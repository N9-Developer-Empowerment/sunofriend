#define PY_SSIZE_T_CLEAN
#include <Python.h>

#if !defined(__APPLE__) || !defined(__MACH__)
#error "Sunofriend's native spawn boundary is supported only on macOS."
#endif

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <spawn.h>
#include <stdbool.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/*
 * PRIVATE NATIVE SECURITY BOUNDARY
 *
 * This CPython extension remains outside setuptools and every public
 * Sunofriend command. The private provenance builder may compile a fresh,
 * hash-pinned artifact for explicit internal canary checks; production worker
 * integration still requires its separate authority and lifecycle gates.
 *
 * The entry point accepts three already-open parent descriptors. It changes no
 * parent descriptor flag or table entry. All descriptor changes below are
 * ordered posix_spawn child file actions.
 */

#ifndef POSIX_SPAWN_CLOEXEC_DEFAULT
#error "The audited Darwin POSIX_SPAWN_CLOEXEC_DEFAULT flag is required."
#endif

#ifndef SUNOFRIEND_NATIVE_SOURCE_SHA256
#error "The audited native source identity is required."
#endif

#ifndef SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256
#error "The audited native build-contract identity is required."
#endif

#define SUNOFRIEND_SCRATCH_FD_MIN 6
#define SUNOFRIEND_EMERGENCY_REAP_ATTEMPTS 200
#define SUNOFRIEND_EMERGENCY_REAP_PAUSE_NS 5000000L

enum {
    SUNOFRIEND_STDIN_FD = 0,
    SUNOFRIEND_STDOUT_FD = 1,
    SUNOFRIEND_STDERR_FD = 2,
    SUNOFRIEND_REQUEST_FD = 3,
    SUNOFRIEND_RESULT_FD = 4,
    SUNOFRIEND_CHECKPOINT_FD = 5,
    SUNOFRIEND_TRANSPORT_COUNT = 3,
};

static const int sunofriend_target_fds[SUNOFRIEND_TRANSPORT_COUNT] = {
    SUNOFRIEND_REQUEST_FD,
    SUNOFRIEND_RESULT_FD,
    SUNOFRIEND_CHECKPOINT_FD,
};

static char *const sunofriend_worker_environment[] = {
    "LANG=C",
    "LC_ALL=C",
    "TZ=UTC",
    NULL,
};

typedef struct {
    PyObject_HEAD
    pid_t pid;
    pid_t owner_pid;
    int wait_status;
    bool spawned;
    bool leader_reaped;
    bool ownership_released;
    bool ownership_lost;
} SunofriendOwnedSpawnChild;

static PyTypeObject SunofriendOwnedSpawnChildType;

static bool
sunofriend_contains_nul(const char *value, Py_ssize_t size)
{
    return memchr(value, '\0', (size_t)size) != NULL;
}

static int
sunofriend_validate_absolute_path(PyObject *path, const char *label)
{
    const char *value;
    Py_ssize_t size;

    if (!PyBytes_CheckExact(path)) {
        PyErr_Format(PyExc_TypeError, "%s must be exact bytes", label);
        return -1;
    }
    value = PyBytes_AS_STRING(path);
    size = PyBytes_GET_SIZE(path);
    if (size < 2 || size > PATH_MAX || value[0] != '/') {
        PyErr_SetString(
            PyExc_ValueError,
            "native spawn paths must be non-root absolute macOS paths"
        );
        return -1;
    }
    if (sunofriend_contains_nul(value, size)) {
        PyErr_Format(PyExc_ValueError, "%s contains NUL", label);
        return -1;
    }
    return 0;
}

static int
sunofriend_validate_transport_fds(const int source_fds[SUNOFRIEND_TRANSPORT_COUNT])
{
    static const int required_access_modes[SUNOFRIEND_TRANSPORT_COUNT] = {
        O_RDONLY,
        O_WRONLY,
        O_RDONLY,
    };
    struct stat backing_nodes[SUNOFRIEND_TRANSPORT_COUNT];
    size_t left;
    size_t right;

    for (left = 0; left < SUNOFRIEND_TRANSPORT_COUNT; left++) {
        if (source_fds[left] < SUNOFRIEND_REQUEST_FD) {
            PyErr_SetString(
                PyExc_ValueError,
                "transport descriptors must be at least 3"
            );
            return -1;
        }
        if (fcntl(source_fds[left], F_GETFD) != FD_CLOEXEC) {
            PyErr_SetString(
                PyExc_ValueError,
                "transport descriptors must be valid and exactly non-inheritable"
            );
            return -1;
        }
        {
            int status_flags = fcntl(source_fds[left], F_GETFL);
            if (status_flags < 0) {
                PyErr_SetFromErrno(PyExc_OSError);
                return -1;
            }
            if (
                (status_flags & O_ACCMODE) != required_access_modes[left]
                || (status_flags & O_APPEND) != 0
                || (
                    /* The retained checkpoint is deliberately opened with
                       O_NONBLOCK by the descriptor inspector.  It is a
                       regular file and the worker reads it with pread(). */
                    left != 2
                    && (status_flags & O_NONBLOCK) != 0
                )
            ) {
                PyErr_SetString(
                    PyExc_ValueError,
                    "transport descriptor access or status flags are invalid"
                );
                return -1;
            }
        }
        if (fstat(source_fds[left], &backing_nodes[left]) != 0) {
            PyErr_SetFromErrno(PyExc_OSError);
            return -1;
        }
        if (!S_ISREG(backing_nodes[left].st_mode)) {
            PyErr_SetString(
                PyExc_ValueError,
                "transport descriptors must reference regular files"
            );
            return -1;
        }
        for (right = left + 1; right < SUNOFRIEND_TRANSPORT_COUNT; right++) {
            if (source_fds[left] == source_fds[right]) {
                PyErr_SetString(PyExc_ValueError, "transport descriptors must be distinct");
                return -1;
            }
        }
    }
    for (left = 0; left < SUNOFRIEND_TRANSPORT_COUNT; left++) {
        for (right = left + 1; right < SUNOFRIEND_TRANSPORT_COUNT; right++) {
            if (
                backing_nodes[left].st_dev == backing_nodes[right].st_dev
                && backing_nodes[left].st_ino == backing_nodes[right].st_ino
            ) {
                PyErr_SetString(
                    PyExc_ValueError,
                    "transport descriptors must have distinct backing nodes"
                );
                return -1;
            }
        }
    }
    return 0;
}

static int
sunofriend_validate_parent_sigchld(void)
{
    struct sigaction disposition;

    if (sigaction(SIGCHLD, NULL, &disposition) != 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return -1;
    }
    if (
        disposition.sa_handler != SIG_DFL
        || (disposition.sa_flags & SA_NOCLDWAIT) != 0
    ) {
        PyErr_SetString(
            PyExc_ValueError,
            "parent SIGCHLD must be default and preserve an owned child"
        );
        return -1;
    }
    return 0;
}

static bool
sunofriend_fd_is_reserved(
    int candidate,
    const int source_fds[SUNOFRIEND_TRANSPORT_COUNT],
    const int scratch_fds[SUNOFRIEND_TRANSPORT_COUNT],
    size_t scratch_count
)
{
    size_t index;

    if (candidate >= SUNOFRIEND_STDIN_FD && candidate <= SUNOFRIEND_CHECKPOINT_FD) {
        return true;
    }
    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        if (candidate == source_fds[index]) {
            return true;
        }
    }
    for (index = 0; index < scratch_count; index++) {
        if (candidate == scratch_fds[index]) {
            return true;
        }
    }
    return false;
}

static int
sunofriend_choose_scratch_fds(
    const int source_fds[SUNOFRIEND_TRANSPORT_COUNT],
    int scratch_fds[SUNOFRIEND_TRANSPORT_COUNT]
)
{
    int candidate = SUNOFRIEND_SCRATCH_FD_MIN;
    size_t index;

    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        while (
            sunofriend_fd_is_reserved(
                candidate,
                source_fds,
                scratch_fds,
                index
            )
        ) {
            if (candidate == INT_MAX) {
                PyErr_SetString(PyExc_OverflowError, "no scratch descriptor is available");
                return -1;
            }
            candidate++;
        }
        scratch_fds[index] = candidate;
        if (candidate < INT_MAX) {
            candidate++;
        }
    }
    return 0;
}

static int
sunofriend_add_child_file_actions(
    posix_spawn_file_actions_t *actions,
    const int source_fds[SUNOFRIEND_TRANSPORT_COUNT],
    const int scratch_fds[SUNOFRIEND_TRANSPORT_COUNT]
)
{
    size_t index;
    int status;

    /*
     * Copy every source first. This makes mappings collision-free even when a
     * source currently occupies fixed target 3, 4, or 5. No operation here
     * runs against the parent descriptor table.
     */
    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        status = posix_spawn_file_actions_adddup2(
            actions,
            source_fds[index],
            scratch_fds[index]
        );
        if (status != 0) {
            return status;
        }
    }

    /*
     * All originals are distinct and at least 3. Close them after staging and
     * before installing the fixed targets, including originals numbered 3,
     * 4, or 5. This leaves no alias of a transport channel in the child.
     */
    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        status = posix_spawn_file_actions_addclose(actions, source_fds[index]);
        if (status != 0) {
            return status;
        }
    }

    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        status = posix_spawn_file_actions_adddup2(
            actions,
            scratch_fds[index],
            sunofriend_target_fds[index]
        );
        if (status != 0) {
            return status;
        }
    }

    /*
     * The fixed 3/4/5 descriptors intentionally cross this exec boundary.
     * The worker must set FD_CLOEXEC on them as its first user-code action.
     */
    for (index = 0; index < SUNOFRIEND_TRANSPORT_COUNT; index++) {
        status = posix_spawn_file_actions_addclose(actions, scratch_fds[index]);
        if (status != 0) {
            return status;
        }
    }

    /*
     * Replace standard streams only after transport mapping is complete.
     * Transport sources are required to be at least 3, so these final actions
     * cannot disturb a source or scratch descriptor.
     */
    status = posix_spawn_file_actions_addopen(
        actions,
        SUNOFRIEND_STDIN_FD,
        "/dev/null",
        O_RDONLY,
        0
    );
    if (status != 0) {
        return status;
    }
    status = posix_spawn_file_actions_addopen(
        actions,
        SUNOFRIEND_STDOUT_FD,
        "/dev/null",
        O_WRONLY,
        0
    );
    if (status != 0) {
        return status;
    }
    status = posix_spawn_file_actions_addopen(
        actions,
        SUNOFRIEND_STDERR_FD,
        "/dev/null",
        O_WRONLY,
        0
    );
    if (status != 0) {
        return status;
    }
    return 0;
}

static int
sunofriend_configure_spawn_attributes(posix_spawnattr_t *attributes)
{
    sigset_t default_signals;
    sigset_t empty_mask;
    short flags = (
        POSIX_SPAWN_CLOEXEC_DEFAULT
        | POSIX_SPAWN_SETPGROUP
        | POSIX_SPAWN_SETSIGDEF
        | POSIX_SPAWN_SETSIGMASK
    );
    int status;

    if (sigfillset(&default_signals) != 0) {
        return errno;
    }
    if (sigdelset(&default_signals, SIGKILL) != 0) {
        return errno;
    }
    if (sigdelset(&default_signals, SIGSTOP) != 0) {
        return errno;
    }
    if (sigemptyset(&empty_mask) != 0) {
        return errno;
    }

    status = posix_spawnattr_setpgroup(attributes, 0);
    if (status != 0) {
        return status;
    }
    status = posix_spawnattr_setsigdefault(attributes, &default_signals);
    if (status != 0) {
        return status;
    }
    status = posix_spawnattr_setsigmask(attributes, &empty_mask);
    if (status != 0) {
        return status;
    }
    return posix_spawnattr_setflags(attributes, flags);
}

static PyObject *
sunofriend_raise_spawn_error(int status, const char *operation)
{
    errno = status;
    PyErr_Format(
        PyExc_OSError,
        "%s failed with errno %d: %s",
        operation,
        status,
        strerror(status)
    );
    return NULL;
}

static void
sunofriend_emergency_kill_and_reap(SunofriendOwnedSpawnChild *child)
{
    int observed_wait_status;
    int attempt;
    pid_t waited;
    struct timespec pause = {
        .tv_sec = 0,
        .tv_nsec = SUNOFRIEND_EMERGENCY_REAP_PAUSE_NS,
    };
    struct timespec remaining_pause;

    /*
     * This is the last-resort object finalizer, not terminal execution
     * evidence. POSIX_SPAWN_SETPGROUP with pgroup 0 makes pid the exact new
     * group. Kill that group, then make a bounded best-effort exact reap if
     * the explicit lifecycle API has not already done so. This finalizer must
     * never perform an unbounded wait while CPython holds the GIL.
     */
    if (!child->leader_reaped) {
        for (;;) {
            waited = waitpid(child->pid, &observed_wait_status, WNOHANG);
            if (waited < 0 && errno == EINTR) {
                continue;
            }
            if (waited == child->pid) {
                child->wait_status = observed_wait_status;
                child->leader_reaped = true;
                child->ownership_released = true;
            } else if (waited < 0 && errno == ECHILD) {
                /*
                 * A competing reaper broke the ownership contract. Never
                 * signal a potentially recycled PID or process-group ID.
                 */
                child->ownership_lost = true;
                return;
            } else if (waited < 0) {
                return;
            }
            break;
        }
    }
    if (child->leader_reaped) {
        return;
    }
    while (kill(-child->pid, SIGKILL) != 0) {
        if (errno == EINTR) {
            continue;
        }
        if (errno != ESRCH) {
            while (kill(child->pid, SIGKILL) != 0 && errno == EINTR) {
            }
        }
        break;
    }
    if (!child->leader_reaped) {
        for (
            attempt = 0;
            attempt < SUNOFRIEND_EMERGENCY_REAP_ATTEMPTS;
            attempt++
        ) {
            waited = waitpid(child->pid, &observed_wait_status, WNOHANG);
            if (waited < 0 && errno == EINTR) {
                continue;
            }
            if (waited == child->pid) {
                child->wait_status = observed_wait_status;
                child->leader_reaped = true;
                child->ownership_released = true;
            } else if (waited < 0 && errno == ECHILD) {
                child->ownership_lost = true;
                break;
            } else if (waited < 0) {
                break;
            } else {
                remaining_pause = pause;
                while (
                    nanosleep(&remaining_pause, &remaining_pause) != 0
                    && errno == EINTR
                ) {
                }
            }
        }
    }
}

static void
sunofriend_owned_child_dealloc(SunofriendOwnedSpawnChild *child)
{
    if (
        child->spawned
        && child->pid > 0
        && child->owner_pid == getpid()
        && !child->ownership_released
        && !child->ownership_lost
    ) {
        sunofriend_emergency_kill_and_reap(child);
    }
    PyObject_Del(child);
}

static PyObject *
sunofriend_owned_child_get_leader_reaped(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    return PyBool_FromLong(child->leader_reaped);
}

static PyObject *
sunofriend_owned_child_get_ownership_released(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    return PyBool_FromLong(child->ownership_released);
}

static PyObject *
sunofriend_owned_child_get_ownership_lost(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    return PyBool_FromLong(child->ownership_lost);
}

static PyObject *
sunofriend_owned_child_wait_nohang(
    SunofriendOwnedSpawnChild *child,
    PyObject *ignored
)
{
    int observed_wait_status;
    pid_t waited;

    (void)ignored;
    if (
        !child->spawned
        || child->pid <= 0
        || child->owner_pid != getpid()
        || child->ownership_lost
    ) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child is not owned by this process"
        );
        return NULL;
    }
    if (child->leader_reaped) {
        return PyLong_FromLong((long)child->wait_status);
    }
    for (;;) {
        waited = waitpid(child->pid, &observed_wait_status, WNOHANG);
        if (waited < 0 && errno == EINTR) {
            continue;
        }
        break;
    }
    if (waited == 0) {
        Py_RETURN_NONE;
    }
    if (waited == child->pid) {
        child->wait_status = observed_wait_status;
        child->leader_reaped = true;
        child->ownership_released = true;
        return PyLong_FromLong((long)child->wait_status);
    }
    if (waited < 0 && errno == ECHILD) {
        child->ownership_lost = true;
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before exact reap"
        );
        return NULL;
    }
    PyErr_SetFromErrno(PyExc_OSError);
    return NULL;
}

static PyObject *
sunofriend_owned_child_signal_group(
    SunofriendOwnedSpawnChild *child,
    PyObject *arguments
)
{
    int observed_wait_status;
    int signal_number;
    int status;
    pid_t waited;

    if (!PyArg_ParseTuple(
        arguments,
        "i:signal_owned_group",
        &signal_number
    )) {
        return NULL;
    }
    if (signal_number != SIGTERM && signal_number != SIGKILL) {
        PyErr_SetString(
            PyExc_ValueError,
            "owned child permits only SIGTERM or SIGKILL"
        );
        return NULL;
    }
    if (
        !child->spawned
        || child->pid <= 0
        || child->owner_pid != getpid()
        || child->ownership_released
        || child->ownership_lost
    ) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child group is not owned"
        );
        return NULL;
    }
    for (;;) {
        waited = waitpid(child->pid, &observed_wait_status, WNOHANG);
        if (waited < 0 && errno == EINTR) {
            continue;
        }
        break;
    }
    if (waited == child->pid) {
        child->wait_status = observed_wait_status;
        child->leader_reaped = true;
        child->ownership_released = true;
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child exact-reaped before group signal"
        );
        return NULL;
    }
    if (waited < 0 && errno == ECHILD) {
        child->ownership_lost = true;
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before group signal"
        );
        return NULL;
    }
    if (waited < 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    for (;;) {
        status = kill(-child->pid, signal_number);
        if (status != 0 && errno == EINTR) {
            continue;
        }
        break;
    }
    if (
        status != 0
        && errno == ESRCH
        && !child->leader_reaped
    ) {
        for (;;) {
            status = kill(child->pid, signal_number);
            if (status != 0 && errno == EINTR) {
                continue;
            }
            break;
        }
    }
    if (status != 0 && errno != ESRCH) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *
sunofriend_owned_child_matches_identity(
    SunofriendOwnedSpawnChild *child,
    PyObject *arguments
)
{
    long reported_pid;
    long reported_pgid;

    if (!PyArg_ParseTuple(
        arguments,
        "ll:matches_pid_and_pgid",
        &reported_pid,
        &reported_pgid
    )) {
        return NULL;
    }
    if (
        !child->spawned
        || child->pid <= 0
        || child->owner_pid != getpid()
        || child->ownership_lost
    ) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child is not owned by this process"
        );
        return NULL;
    }
    return PyBool_FromLong(
        reported_pid == (long)child->pid
        && reported_pgid == (long)child->pid
    );
}

static PyMethodDef sunofriend_owned_child_methods[] = {
    {
        "wait_nohang",
        (PyCFunction)sunofriend_owned_child_wait_nohang,
        METH_NOARGS,
        PyDoc_STR(
            "Exact-PID nonblocking wait; retained while running, then cached."
        ),
    },
    {
        "signal_owned_group",
        (PyCFunction)sunofriend_owned_child_signal_group,
        METH_VARARGS,
        PyDoc_STR("Signal the owned process group with SIGTERM or SIGKILL."),
    },
    {
        "matches_pid_and_pgid",
        (PyCFunction)sunofriend_owned_child_matches_identity,
        METH_VARARGS,
        PyDoc_STR("Confirm reported PID/PGID without exposing child authority."),
    },
    {NULL, NULL, 0, NULL},
};

static PyGetSetDef sunofriend_owned_child_getset[] = {
    {
        "leader_reaped",
        (getter)sunofriend_owned_child_get_leader_reaped,
        NULL,
        PyDoc_STR("Whether this owner exact-reaped the child leader."),
        NULL,
    },
    {
        "ownership_released",
        (getter)sunofriend_owned_child_get_ownership_released,
        NULL,
        PyDoc_STR("Whether exact leader ownership ended by successful reap."),
        NULL,
    },
    {
        "ownership_lost",
        (getter)sunofriend_owned_child_get_ownership_lost,
        NULL,
        PyDoc_STR("Whether exact child ownership was stolen or invalidated."),
        NULL,
    },
    {NULL, NULL, NULL, NULL, NULL},
};

static PyTypeObject SunofriendOwnedSpawnChildType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_separation_native_spawn_darwin._OwnedSpawnChild",
    .tp_basicsize = sizeof(SunofriendOwnedSpawnChild),
    .tp_dealloc = (destructor)sunofriend_owned_child_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = PyDoc_STR(
        "Private nonconstructible exact-child ownership handle."
    ),
    .tp_methods = sunofriend_owned_child_methods,
    .tp_getset = sunofriend_owned_child_getset,
};

static PyObject *
sunofriend_spawn_bound_fake_worker(PyObject *self, PyObject *arguments)
{
    PyObject *bound_executable;
    PyObject *bound_worker_entrypoint;
    char *native_arguments[6];
    int source_fds[SUNOFRIEND_TRANSPORT_COUNT];
    int scratch_fds[SUNOFRIEND_TRANSPORT_COUNT];
    posix_spawn_file_actions_t file_actions;
    posix_spawnattr_t attributes;
    bool file_actions_ready = false;
    bool attributes_ready = false;
    const char *failed_operation = "posix_spawn";
    SunofriendOwnedSpawnChild *owned_child;
    pid_t child_pid = -1;
    int status;

    (void)self;
    if (!PyArg_ParseTuple(
        arguments,
        "O!O!iii:_spawn_bound_fake_worker",
        &PyBytes_Type,
        &bound_executable,
        &PyBytes_Type,
        &bound_worker_entrypoint,
        &source_fds[0],
        &source_fds[1],
        &source_fds[2]
    )) {
        return NULL;
    }
    if (
        sunofriend_validate_absolute_path(
            bound_executable,
            "bound executable"
        ) != 0
        || sunofriend_validate_absolute_path(
            bound_worker_entrypoint,
            "bound worker entrypoint"
        ) != 0
        || sunofriend_validate_transport_fds(source_fds) != 0
        || sunofriend_validate_parent_sigchld() != 0
        || sunofriend_choose_scratch_fds(source_fds, scratch_fds) != 0
    ) {
        return NULL;
    }
    native_arguments[0] = PyBytes_AS_STRING(bound_executable);
    native_arguments[1] = "-I";
    native_arguments[2] = "-B";
    native_arguments[3] = "-S";
    native_arguments[4] = PyBytes_AS_STRING(bound_worker_entrypoint);
    native_arguments[5] = NULL;

    owned_child = PyObject_New(
        SunofriendOwnedSpawnChild,
        &SunofriendOwnedSpawnChildType
    );
    if (owned_child == NULL) {
        return NULL;
    }
    owned_child->pid = -1;
    owned_child->owner_pid = getpid();
    owned_child->wait_status = 0;
    owned_child->spawned = false;
    owned_child->leader_reaped = false;
    owned_child->ownership_released = false;
    owned_child->ownership_lost = false;

    status = posix_spawn_file_actions_init(&file_actions);
    if (status != 0) {
        failed_operation = "posix_spawn_file_actions_init";
        goto fail;
    }
    file_actions_ready = true;
    status = sunofriend_add_child_file_actions(
        &file_actions,
        source_fds,
        scratch_fds
    );
    if (status != 0) {
        failed_operation = "posix_spawn_file_actions";
        goto fail;
    }

    status = posix_spawnattr_init(&attributes);
    if (status != 0) {
        failed_operation = "posix_spawnattr_init";
        goto fail;
    }
    attributes_ready = true;
    status = sunofriend_configure_spawn_attributes(&attributes);
    if (status != 0) {
        failed_operation = "posix_spawnattr";
        goto fail;
    }

    status = posix_spawn(
        &child_pid,
        PyBytes_AS_STRING(bound_executable),
        &file_actions,
        &attributes,
        native_arguments,
        sunofriend_worker_environment
    );
    if (status != 0) {
        failed_operation = "posix_spawn";
        goto fail;
    }
    owned_child->pid = child_pid;
    owned_child->spawned = true;

    (void)posix_spawnattr_destroy(&attributes);
    (void)posix_spawn_file_actions_destroy(&file_actions);
    return (PyObject *)owned_child;

fail:
    if (attributes_ready) {
        (void)posix_spawnattr_destroy(&attributes);
    }
    if (file_actions_ready) {
        (void)posix_spawn_file_actions_destroy(&file_actions);
    }
    Py_DECREF(owned_child);
    return sunofriend_raise_spawn_error(status, failed_operation);
}

static PyMethodDef sunofriend_spawn_methods[] = {
    {
        "_spawn_bound_fake_worker",
        sunofriend_spawn_bound_fake_worker,
        METH_VARARGS,
        PyDoc_STR(
            "Private audited spawn boundary; production worker integration "
            "remains unavailable."
        ),
    },
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef sunofriend_spawn_module = {
    PyModuleDef_HEAD_INIT,
    "_separation_native_spawn_darwin",
    "Private provenance-built Darwin spawn boundary.",
    -1,
    sunofriend_spawn_methods,
    NULL,
    NULL,
    NULL,
    NULL,
};

PyMODINIT_FUNC
PyInit__separation_native_spawn_darwin(void)
{
    PyObject *module = PyModule_Create(&sunofriend_spawn_module);

    if (module == NULL) {
        return NULL;
    }
    if (PyType_Ready(&SunofriendOwnedSpawnChildType) != 0) {
        Py_DECREF(module);
        return NULL;
    }
    Py_INCREF(&SunofriendOwnedSpawnChildType);
    if (
        PyModule_AddObject(
            module,
            "_OwnedSpawnChild",
            (PyObject *)&SunofriendOwnedSpawnChildType
        ) != 0
    ) {
        Py_DECREF(&SunofriendOwnedSpawnChildType);
        Py_DECREF(module);
        return NULL;
    }
    if (
        PyModule_AddStringConstant(
            module,
            "_SUNOFRIEND_NATIVE_SOURCE_SHA256",
            SUNOFRIEND_NATIVE_SOURCE_SHA256
        ) != 0
        || PyModule_AddStringConstant(
            module,
            "_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",
            SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256
        ) != 0
    ) {
        Py_DECREF(module);
        return NULL;
    }
    return module;
}
