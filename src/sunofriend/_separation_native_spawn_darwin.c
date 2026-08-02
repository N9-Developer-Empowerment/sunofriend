#define PY_SSIZE_T_CLEAN
#include <Python.h>

#if !defined(__APPLE__) || !defined(__MACH__)
#error "Sunofriend's native spawn boundary is supported only on macOS."
#endif

#include <errno.h>
#include <fcntl.h>
#include <libproc.h>
#include <limits.h>
#include <signal.h>
#include <spawn.h>
#include <stdbool.h>
#include <stdint.h>
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
 * The fixed entry points accept either the three data descriptors or those
 * three descriptors plus the existing Kim ready/release pipe pair. They
 * change no parent descriptor flag or table entry. All descriptor changes
 * below are ordered posix_spawn child file actions.
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

#define SUNOFRIEND_GROUP_MEMBER_LIMIT 1024
#define SUNOFRIEND_EMERGENCY_REAP_ATTEMPTS 200
#define SUNOFRIEND_EMERGENCY_REAP_PAUSE_NS 5000000L
#define SUNOFRIEND_PROCESS_IMAGE_OBSERVATION_SECONDS 2
#define SUNOFRIEND_PROCESS_IMAGE_POLL_PAUSE_NS 10000000L
#define SUNOFRIEND_CDHASH_BYTES 20
#define SUNOFRIEND_CDHASH_HEX_BYTES 40
#define SUNOFRIEND_CS_OPS_CDHASH 5
#define SUNOFRIEND_EXECUTABLE_REGION_LIMIT 4096
#define SUNOFRIEND_VM_PROT_EXECUTE 0x04

/* csops is exported by Darwin's libSystem but is not declared by the public
 * SDK headers consumed by this deliberately small extension. */
extern int csops(pid_t pid, unsigned int operations, void *output, size_t size);

enum {
    SUNOFRIEND_STDIN_FD = 0,
    SUNOFRIEND_STDOUT_FD = 1,
    SUNOFRIEND_STDERR_FD = 2,
    SUNOFRIEND_REQUEST_FD = 3,
    SUNOFRIEND_RESULT_FD = 4,
    SUNOFRIEND_CHECKPOINT_FD = 5,
    SUNOFRIEND_READY_FD = 6,
    SUNOFRIEND_RELEASE_FD = 7,
    SUNOFRIEND_DATA_TRANSPORT_COUNT = 3,
    SUNOFRIEND_READY_RELEASE_TRANSPORT_COUNT = 5,
    SUNOFRIEND_MAX_TRANSPORT_COUNT = 5,
};

enum {
    SUNOFRIEND_NO_START_NONE = 0,
    SUNOFRIEND_NO_START_FILE_ACTIONS_INIT = 1,
    SUNOFRIEND_NO_START_FILE_ACTIONS = 2,
    SUNOFRIEND_NO_START_ATTRIBUTES_INIT = 3,
    SUNOFRIEND_NO_START_ATTRIBUTES = 4,
    SUNOFRIEND_NO_START_POSIX_SPAWN = 5,
};

static const int sunofriend_target_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT] = {
    SUNOFRIEND_REQUEST_FD,
    SUNOFRIEND_RESULT_FD,
    SUNOFRIEND_CHECKPOINT_FD,
    SUNOFRIEND_READY_FD,
    SUNOFRIEND_RELEASE_FD,
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
    int no_start_stage;
    int native_status;
    bool spawned;
    bool leader_exit_observed;
    bool leader_reaped;
    bool group_empty;
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
sunofriend_validate_cdhash(PyObject *value)
{
    const unsigned char *text;
    Py_ssize_t index;

    if (
        !PyBytes_CheckExact(value)
        || PyBytes_GET_SIZE(value) != SUNOFRIEND_CDHASH_HEX_BYTES
    ) {
        PyErr_SetString(
            PyExc_ValueError,
            "expected process-image CDHash must be 40 lowercase hex bytes"
        );
        return -1;
    }
    text = (const unsigned char *)PyBytes_AS_STRING(value);
    for (index = 0; index < SUNOFRIEND_CDHASH_HEX_BYTES; index++) {
        if (
            !(
                (text[index] >= (unsigned char)'0'
                 && text[index] <= (unsigned char)'9')
                || (text[index] >= (unsigned char)'a'
                    && text[index] <= (unsigned char)'f')
            )
        ) {
            PyErr_SetString(
                PyExc_ValueError,
                "expected process-image CDHash must be 40 lowercase hex bytes"
            );
            return -1;
        }
    }
    return 0;
}

static void
sunofriend_cdhash_to_hex(
    const unsigned char input[SUNOFRIEND_CDHASH_BYTES],
    char output[SUNOFRIEND_CDHASH_HEX_BYTES + 1]
)
{
    static const char hexadecimal[] = "0123456789abcdef";
    size_t index;

    for (index = 0; index < SUNOFRIEND_CDHASH_BYTES; index++) {
        output[index * 2] = hexadecimal[input[index] >> 4];
        output[index * 2 + 1] = hexadecimal[input[index] & 0x0f];
    }
    output[SUNOFRIEND_CDHASH_HEX_BYTES] = '\0';
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
sunofriend_validate_transport_fds(
    const int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    size_t transport_count
)
{
    static const int required_access_modes[SUNOFRIEND_MAX_TRANSPORT_COUNT] = {
        O_RDONLY,
        O_WRONLY,
        O_RDONLY,
        O_WRONLY,
        O_RDONLY,
    };
    struct stat backing_nodes[SUNOFRIEND_MAX_TRANSPORT_COUNT];
    size_t left;
    size_t right;

    if (
        transport_count != SUNOFRIEND_DATA_TRANSPORT_COUNT
        && transport_count != SUNOFRIEND_READY_RELEASE_TRANSPORT_COUNT
    ) {
        PyErr_SetString(PyExc_ValueError, "transport descriptor count differs");
        return -1;
    }
    for (left = 0; left < transport_count; left++) {
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
        if (
            (left < SUNOFRIEND_DATA_TRANSPORT_COUNT
             && !S_ISREG(backing_nodes[left].st_mode))
            || (left >= SUNOFRIEND_DATA_TRANSPORT_COUNT
                && !S_ISFIFO(backing_nodes[left].st_mode))
        ) {
            PyErr_SetString(
                PyExc_ValueError,
                "data transports must be regular files and readiness "
                "transports must be pipes"
            );
            return -1;
        }
        for (right = left + 1; right < transport_count; right++) {
            if (source_fds[left] == source_fds[right]) {
                PyErr_SetString(PyExc_ValueError, "transport descriptors must be distinct");
                return -1;
            }
        }
    }
    for (left = 0; left < transport_count; left++) {
        for (right = left + 1; right < transport_count; right++) {
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
    const int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    const int scratch_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    size_t transport_count,
    size_t scratch_count
)
{
    size_t index;

    for (index = 0; index < transport_count; index++) {
        if (candidate == sunofriend_target_fds[index]) {
            return true;
        }
    }
    for (index = 0; index < transport_count; index++) {
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
    const int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    int scratch_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    size_t transport_count
)
{
    int candidate = sunofriend_target_fds[transport_count - 1] + 1;
    size_t index;

    for (index = 0; index < transport_count; index++) {
        while (
            sunofriend_fd_is_reserved(
                candidate,
                source_fds,
                scratch_fds,
                transport_count,
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
    const int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    const int scratch_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    size_t transport_count
)
{
    size_t index;
    int status;

    /*
     * Copy every source first. This makes mappings collision-free even when a
     * source currently occupies one of its fixed targets. No operation here
     * runs against the parent descriptor table.
     */
    for (index = 0; index < transport_count; index++) {
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
     * 4, 5, 6 or 7. This leaves no alias of a transport channel in the child.
     */
    for (index = 0; index < transport_count; index++) {
        status = posix_spawn_file_actions_addclose(actions, source_fds[index]);
        if (status != 0) {
            return status;
        }
    }

    for (index = 0; index < transport_count; index++) {
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
     * The fixed data and optional ready/release descriptors intentionally
     * cross this exec boundary.
     * The worker must set FD_CLOEXEC on them as its first user-code action.
     */
    for (index = 0; index < transport_count; index++) {
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
        | POSIX_SPAWN_SETSID
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

static int
sunofriend_poll_owned_terminal(
    SunofriendOwnedSpawnChild *child,
    bool *terminal
)
{
    pid_t group_members[SUNOFRIEND_GROUP_MEMBER_LIMIT];
    siginfo_t exit_information;
    int group_member_count;
    int observed_wait_status;
    pid_t waited;

    *terminal = false;
    if (child->leader_reaped) {
        if (
            child->group_empty
            && child->ownership_released
            && !child->ownership_lost
        ) {
            *terminal = true;
            return 0;
        }
        return EINVAL;
    }
    if (!child->leader_exit_observed) {
        memset(&exit_information, 0, sizeof(exit_information));
        for (;;) {
            if (
                waitid(
                    P_PID,
                    (id_t)child->pid,
                    &exit_information,
                    WEXITED | WNOHANG | WNOWAIT
                ) == 0
            ) {
                break;
            }
            if (errno != EINTR) {
                if (errno == ECHILD) {
                    child->ownership_lost = true;
                }
                return errno;
            }
        }
        if (exit_information.si_pid == 0) {
            return 0;
        }
        if (exit_information.si_pid != child->pid) {
            child->ownership_lost = true;
            return ECHILD;
        }
        child->leader_exit_observed = true;
    }

    errno = 0;
    group_member_count = proc_listpgrppids(
        child->pid,
        group_members,
        (int)sizeof(group_members)
    );
    if (group_member_count < 0) {
        return errno != 0 ? errno : EIO;
    }
    if (group_member_count >= SUNOFRIEND_GROUP_MEMBER_LIMIT) {
        return EOVERFLOW;
    }
    if (
        group_member_count != 1
        || group_members[0] != child->pid
    ) {
        return 0;
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
        child->group_empty = true;
        child->ownership_released = true;
        *terminal = true;
        return 0;
    }
    if (waited < 0 && errno == ECHILD) {
        child->ownership_lost = true;
        return ECHILD;
    }
    if (waited < 0) {
        return errno;
    }
    return EAGAIN;
}

static void
sunofriend_emergency_kill_and_reap(SunofriendOwnedSpawnChild *child)
{
    bool terminal = false;
    int attempt;
    int status;
    struct timespec pause = {
        .tv_sec = 0,
        .tv_nsec = SUNOFRIEND_EMERGENCY_REAP_PAUSE_NS,
    };
    struct timespec remaining_pause;

    /*
     * This is the last-resort object finalizer, not terminal execution
     * evidence. POSIX_SPAWN_SETSID makes pid the exact private session and
     * process-group leader. Observe exit without reaping, retain that zombie
     * leader so its numeric group cannot be recycled, kill the whole group,
     * and exact-reap only after libproc reports that no descendant remains.
     * This finalizer must never perform an unbounded wait while CPython holds
     * the GIL.
     */
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (terminal || child->ownership_lost) {
        return;
    }
    while (kill(-child->pid, SIGKILL) != 0) {
        if (errno == EINTR) {
            continue;
        }
        break;
    }
    for (
        attempt = 0;
        attempt < SUNOFRIEND_EMERGENCY_REAP_ATTEMPTS;
        attempt++
    ) {
        status = sunofriend_poll_owned_terminal(child, &terminal);
        if (terminal || child->ownership_lost) {
            return;
        }
        remaining_pause = pause;
        while (
            nanosleep(&remaining_pause, &remaining_pause) != 0
            && errno == EINTR
        ) {
        }
    }
    (void)status;
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
sunofriend_owned_child_get_start_state(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    if (child->spawned) {
        return PyUnicode_FromString("started_owned");
    }
    if (
        child->native_status > 0
        && child->no_start_stage != SUNOFRIEND_NO_START_NONE
    ) {
        return PyUnicode_FromString("not_started");
    }
    return PyUnicode_FromString("invalid");
}

static PyObject *
sunofriend_owned_child_get_no_start_stage(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    const char *stage;

    (void)closure;
    switch (child->no_start_stage) {
        case SUNOFRIEND_NO_START_FILE_ACTIONS_INIT:
            stage = "file_actions_init";
            break;
        case SUNOFRIEND_NO_START_FILE_ACTIONS:
            stage = "file_actions";
            break;
        case SUNOFRIEND_NO_START_ATTRIBUTES_INIT:
            stage = "attributes_init";
            break;
        case SUNOFRIEND_NO_START_ATTRIBUTES:
            stage = "attributes";
            break;
        case SUNOFRIEND_NO_START_POSIX_SPAWN:
            stage = "posix_spawn";
            break;
        default:
            Py_RETURN_NONE;
    }
    return PyUnicode_FromString(stage);
}

static PyObject *
sunofriend_owned_child_get_native_status(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    if (child->native_status <= 0) {
        Py_RETURN_NONE;
    }
    return PyLong_FromLong((long)child->native_status);
}

static PyObject *
sunofriend_owned_child_get_leader_exit_observed(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    return PyBool_FromLong(child->leader_exit_observed);
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
sunofriend_owned_child_get_group_empty(
    SunofriendOwnedSpawnChild *child,
    void *closure
)
{
    (void)closure;
    return PyBool_FromLong(child->group_empty);
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
    bool terminal;
    int status;

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
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (status == ECHILD && child->ownership_lost) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before exact group terminality"
        );
        return NULL;
    }
    if (status != 0) {
        errno = status;
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    if (terminal) {
        return PyLong_FromLong((long)child->wait_status);
    }
    Py_RETURN_NONE;
}

static PyObject *
sunofriend_owned_child_signal_group(
    SunofriendOwnedSpawnChild *child,
    PyObject *arguments
)
{
    bool terminal;
    int signal_number;
    int status;

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
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (terminal) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child group became terminal before group signal"
        );
        return NULL;
    }
    if (status == ECHILD && child->ownership_lost) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before group signal"
        );
        return NULL;
    }
    if (status != 0) {
        errno = status;
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
    if (status != 0) {
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

static PyObject *
sunofriend_owned_child_observe_process_image(
    SunofriendOwnedSpawnChild *child,
    PyObject *arguments
)
{
    PyObject *runtime_launcher;
    PyObject *expected_process_image;
    PyObject *expected_cdhash;
    const char *launcher_path;
    const char *expected_path;
    const char *expected_cdhash_text;
    char current_path[PROC_PIDPATHINFO_MAXSIZE];
    unsigned char kernel_cdhash[SUNOFRIEND_CDHASH_BYTES];
    char kernel_cdhash_text[SUNOFRIEND_CDHASH_HEX_BYTES + 1];
    struct timespec deadline;
    struct timespec now;
    struct timespec pause = {
        .tv_sec = 0,
        .tv_nsec = SUNOFRIEND_PROCESS_IMAGE_POLL_PAUSE_NS,
    };
    struct timespec remaining_pause;
    bool terminal = false;
    int path_bytes;
    int status;

    if (!PyArg_ParseTuple(
        arguments,
        "O!O!O!:observe_owned_process_image",
        &PyBytes_Type,
        &runtime_launcher,
        &PyBytes_Type,
        &expected_process_image,
        &PyBytes_Type,
        &expected_cdhash
    )) {
        return NULL;
    }
    if (
        sunofriend_validate_absolute_path(
            runtime_launcher,
            "runtime launcher"
        ) != 0
        || sunofriend_validate_absolute_path(
            expected_process_image,
            "expected process image"
        ) != 0
        || sunofriend_validate_cdhash(expected_cdhash) != 0
    ) {
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
            "native child process image is not owned"
        );
        return NULL;
    }
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (status == ECHILD && child->ownership_lost) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before process-image observation"
        );
        return NULL;
    }
    if (status != 0) {
        errno = status;
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    if (terminal || child->leader_exit_observed) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child exited before process-image observation"
        );
        return NULL;
    }
    if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    deadline.tv_sec += SUNOFRIEND_PROCESS_IMAGE_OBSERVATION_SECONDS;
    launcher_path = PyBytes_AS_STRING(runtime_launcher);
    expected_path = PyBytes_AS_STRING(expected_process_image);
    expected_cdhash_text = PyBytes_AS_STRING(expected_cdhash);

    for (;;) {
        memset(current_path, 0, sizeof(current_path));
        errno = 0;
        path_bytes = proc_pidpath(
            child->pid,
            current_path,
            (uint32_t)sizeof(current_path)
        );
        if (path_bytes > 0) {
            if ((size_t)path_bytes >= sizeof(current_path)) {
                PyErr_SetString(
                    PyExc_RuntimeError,
                    "native child process image path exceeded its bound"
                );
                return NULL;
            }
            current_path[path_bytes] = '\0';
            if (strcmp(current_path, expected_path) == 0) {
                memset(kernel_cdhash, 0, sizeof(kernel_cdhash));
                if (
                    csops(
                        child->pid,
                        SUNOFRIEND_CS_OPS_CDHASH,
                        kernel_cdhash,
                        sizeof(kernel_cdhash)
                    ) != 0
                ) {
                    if (errno != ESRCH && errno != EINVAL) {
                        PyErr_SetFromErrno(PyExc_OSError);
                        return NULL;
                    }
                } else {
                    sunofriend_cdhash_to_hex(
                        kernel_cdhash,
                        kernel_cdhash_text
                    );
                    if (
                        memcmp(
                            kernel_cdhash_text,
                            expected_cdhash_text,
                            SUNOFRIEND_CDHASH_HEX_BYTES
                        ) != 0
                    ) {
                        PyErr_SetString(
                            PyExc_RuntimeError,
                            "native child process image CDHash differs"
                        );
                        return NULL;
                    }
                    return Py_BuildValue(
                        "{s:s,s:s}",
                        "kernel_cdhash",
                        kernel_cdhash_text,
                        "path_state",
                        "matched_expected_process_image"
                    );
                }
            } else if (strcmp(current_path, launcher_path) != 0) {
                PyErr_SetString(
                    PyExc_RuntimeError,
                    "native child process image path differs"
                );
                return NULL;
            }
        } else if (errno != ESRCH && errno != EINVAL) {
            PyErr_SetFromErrno(PyExc_OSError);
            return NULL;
        }
        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
            PyErr_SetFromErrno(PyExc_OSError);
            return NULL;
        }
        if (
            now.tv_sec > deadline.tv_sec
            || (
                now.tv_sec == deadline.tv_sec
                && now.tv_nsec >= deadline.tv_nsec
            )
        ) {
            PyErr_SetString(
                PyExc_TimeoutError,
                "native child process image observation timed out"
            );
            return NULL;
        }
        remaining_pause = pause;
        while (
            nanosleep(&remaining_pause, &remaining_pause) != 0
            && errno == EINTR
        ) {
        }
    }
}

static PyObject *
sunofriend_owned_child_snapshot_executable_regions(
    SunofriendOwnedSpawnChild *child,
    PyObject *ignored
)
{
    PyObject *regions;
    PyObject *entry;
    PyObject *path;
    struct proc_regionwithpathinfo output;
    uint64_t address = 0;
    uint64_t next_address;
    size_t path_bytes;
    bool terminal = false;
    int result;
    int status;
    int index;

    (void)ignored;
    if (
        !child->spawned
        || child->pid <= 0
        || child->owner_pid != getpid()
        || child->ownership_released
        || child->ownership_lost
    ) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child executable regions are not owned"
        );
        return NULL;
    }
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (status == ECHILD && child->ownership_lost) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost before executable-region snapshot"
        );
        return NULL;
    }
    if (status != 0) {
        errno = status;
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    if (terminal || child->leader_exit_observed) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child exited before executable-region snapshot"
        );
        return NULL;
    }

    regions = PyList_New(0);
    if (regions == NULL) {
        return NULL;
    }
    for (index = 0; index < SUNOFRIEND_EXECUTABLE_REGION_LIMIT; index++) {
        memset(&output, 0, sizeof(output));
        errno = 0;
        result = proc_pidinfo(
            child->pid,
            PROC_PIDREGIONPATHINFO,
            address,
            &output,
            (int)sizeof(output)
        );
        if (result <= 0) {
            if (errno == 0 || errno == EINVAL) {
                break;
            }
            if (errno == ESRCH) {
                PyErr_SetString(
                    PyExc_RuntimeError,
                    "native child exited during executable-region snapshot"
                );
            } else {
                PyErr_SetFromErrno(PyExc_OSError);
            }
            goto fail;
        }
        if (result != (int)sizeof(output)) {
            PyErr_SetString(
                PyExc_RuntimeError,
                "native executable-region result size differs"
            );
            goto fail;
        }
        if (
            output.prp_prinfo.pri_size == 0
            || output.prp_prinfo.pri_address > UINT64_MAX
                - output.prp_prinfo.pri_size
        ) {
            PyErr_SetString(
                PyExc_RuntimeError,
                "native executable-region traversal did not advance"
            );
            goto fail;
        }
        next_address = output.prp_prinfo.pri_address
            + output.prp_prinfo.pri_size;
        if (next_address <= address) {
            PyErr_SetString(
                PyExc_RuntimeError,
                "native executable-region traversal did not advance"
            );
            goto fail;
        }
        address = next_address;
        if (
            (output.prp_prinfo.pri_protection & SUNOFRIEND_VM_PROT_EXECUTE)
            == 0
        ) {
            continue;
        }
        path_bytes = strnlen(
            output.prp_vip.vip_path,
            sizeof(output.prp_vip.vip_path)
        );
        if (path_bytes == sizeof(output.prp_vip.vip_path)) {
            PyErr_SetString(
                PyExc_RuntimeError,
                "native executable-region path exceeded its bound"
            );
            goto fail;
        }
        if (path_bytes == 0) {
            path = Py_None;
            Py_INCREF(path);
        } else {
            path = PyBytes_FromStringAndSize(
                output.prp_vip.vip_path,
                (Py_ssize_t)path_bytes
            );
        }
        if (path == NULL) {
            goto fail;
        }
        entry = Py_BuildValue(
            "(OKKKI)",
            path,
            (unsigned long long)output.prp_prinfo.pri_address,
            (unsigned long long)output.prp_prinfo.pri_size,
            (unsigned long long)output.prp_prinfo.pri_offset,
            (unsigned int)output.prp_prinfo.pri_protection
        );
        Py_DECREF(path);
        if (entry == NULL) {
            goto fail;
        }
        if (PyList_Append(regions, entry) != 0) {
            Py_DECREF(entry);
            goto fail;
        }
        Py_DECREF(entry);
    }
    if (index == SUNOFRIEND_EXECUTABLE_REGION_LIMIT) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native executable-region count exceeded its bound"
        );
        goto fail;
    }
    if (PyList_GET_SIZE(regions) == 0) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native executable-region snapshot is empty"
        );
        goto fail;
    }
    status = sunofriend_poll_owned_terminal(child, &terminal);
    if (status == ECHILD && child->ownership_lost) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child ownership was lost during executable-region snapshot"
        );
        goto fail;
    }
    if (status != 0) {
        errno = status;
        PyErr_SetFromErrno(PyExc_OSError);
        goto fail;
    }
    if (terminal || child->leader_exit_observed) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "native child exited during executable-region snapshot"
        );
        goto fail;
    }
    entry = PyList_AsTuple(regions);
    Py_DECREF(regions);
    return entry;

fail:
    Py_DECREF(regions);
    return NULL;
}

static PyMethodDef sunofriend_owned_child_methods[] = {
    {
        "wait_nohang",
        (PyCFunction)sunofriend_owned_child_wait_nohang,
        METH_NOARGS,
        PyDoc_STR(
            "Nonblocking private-group drain and exact leader reap; then cached."
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
    {
        "observe_owned_process_image",
        (PyCFunction)sunofriend_owned_child_observe_process_image,
        METH_VARARGS,
        PyDoc_STR(
            "Verify the owned live process image and kernel CDHash without "
            "exposing PID authority."
        ),
    },
    {
        "snapshot_owned_executable_regions",
        (PyCFunction)sunofriend_owned_child_snapshot_executable_regions,
        METH_NOARGS,
        PyDoc_STR(
            "Snapshot executable regions of the exact owned live child "
            "without exposing PID authority."
        ),
    },
    {NULL, NULL, 0, NULL},
};

static PyGetSetDef sunofriend_owned_child_getset[] = {
    {
        "start_state",
        (getter)sunofriend_owned_child_get_start_state,
        NULL,
        PyDoc_STR("Whether native spawn started one exactly owned child."),
        NULL,
    },
    {
        "no_start_stage",
        (getter)sunofriend_owned_child_get_no_start_stage,
        NULL,
        PyDoc_STR("Code-owned native stage when no child was started."),
        NULL,
    },
    {
        "native_status",
        (getter)sunofriend_owned_child_get_native_status,
        NULL,
        PyDoc_STR("Private nonzero native status for a no-start outcome."),
        NULL,
    },
    {
        "leader_exit_observed",
        (getter)sunofriend_owned_child_get_leader_exit_observed,
        NULL,
        PyDoc_STR("Whether leader exit was observed without reaping it."),
        NULL,
    },
    {
        "leader_reaped",
        (getter)sunofriend_owned_child_get_leader_reaped,
        NULL,
        PyDoc_STR("Whether this owner exact-reaped the child leader."),
        NULL,
    },
    {
        "group_empty",
        (getter)sunofriend_owned_child_get_group_empty,
        NULL,
        PyDoc_STR("Whether the private process group was proven empty."),
        NULL,
    },
    {
        "ownership_released",
        (getter)sunofriend_owned_child_get_ownership_released,
        NULL,
        PyDoc_STR("Whether group emptiness and exact leader reap released ownership."),
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
sunofriend_spawn_bound_worker(
    PyObject *bound_executable,
    PyObject *bound_worker_entrypoint,
    const int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT],
    size_t transport_count
)
{
    char *native_arguments[6];
    int scratch_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT];
    posix_spawn_file_actions_t file_actions;
    posix_spawnattr_t attributes;
    bool file_actions_ready = false;
    bool attributes_ready = false;
    int no_start_stage = SUNOFRIEND_NO_START_NONE;
    SunofriendOwnedSpawnChild *owned_child;
    pid_t child_pid = -1;
    int status;

    if (
        sunofriend_validate_absolute_path(
            bound_executable,
            "bound executable"
        ) != 0
        || sunofriend_validate_absolute_path(
            bound_worker_entrypoint,
            "bound worker entrypoint"
        ) != 0
        || sunofriend_validate_transport_fds(source_fds, transport_count) != 0
        || sunofriend_validate_parent_sigchld() != 0
        || sunofriend_choose_scratch_fds(
            source_fds,
            scratch_fds,
            transport_count
        ) != 0
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
    owned_child->no_start_stage = SUNOFRIEND_NO_START_NONE;
    owned_child->native_status = 0;
    owned_child->spawned = false;
    owned_child->leader_exit_observed = false;
    owned_child->leader_reaped = false;
    owned_child->group_empty = false;
    owned_child->ownership_released = false;
    owned_child->ownership_lost = false;

    status = posix_spawn_file_actions_init(&file_actions);
    if (status != 0) {
        no_start_stage = SUNOFRIEND_NO_START_FILE_ACTIONS_INIT;
        goto fail;
    }
    file_actions_ready = true;
    status = sunofriend_add_child_file_actions(
        &file_actions,
        source_fds,
        scratch_fds,
        transport_count
    );
    if (status != 0) {
        no_start_stage = SUNOFRIEND_NO_START_FILE_ACTIONS;
        goto fail;
    }

    status = posix_spawnattr_init(&attributes);
    if (status != 0) {
        no_start_stage = SUNOFRIEND_NO_START_ATTRIBUTES_INIT;
        goto fail;
    }
    attributes_ready = true;
    status = sunofriend_configure_spawn_attributes(&attributes);
    if (status != 0) {
        no_start_stage = SUNOFRIEND_NO_START_ATTRIBUTES;
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
        no_start_stage = SUNOFRIEND_NO_START_POSIX_SPAWN;
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
    owned_child->no_start_stage = no_start_stage;
    owned_child->native_status = status;
    return (PyObject *)owned_child;
}

static PyObject *
sunofriend_spawn_bound_fake_worker(PyObject *self, PyObject *arguments)
{
    PyObject *bound_executable;
    PyObject *bound_worker_entrypoint;
    int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT] = {-1, -1, -1, -1, -1};

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
    return sunofriend_spawn_bound_worker(
        bound_executable,
        bound_worker_entrypoint,
        source_fds,
        SUNOFRIEND_DATA_TRANSPORT_COUNT
    );
}

static PyObject *
sunofriend_spawn_bound_fake_worker_with_ready_release(
    PyObject *self,
    PyObject *arguments
)
{
    PyObject *bound_executable;
    PyObject *bound_worker_entrypoint;
    int source_fds[SUNOFRIEND_MAX_TRANSPORT_COUNT];

    (void)self;
    if (!PyArg_ParseTuple(
        arguments,
        "O!O!iiiii:_spawn_bound_fake_worker_with_ready_release",
        &PyBytes_Type,
        &bound_executable,
        &PyBytes_Type,
        &bound_worker_entrypoint,
        &source_fds[0],
        &source_fds[1],
        &source_fds[2],
        &source_fds[3],
        &source_fds[4]
    )) {
        return NULL;
    }
    return sunofriend_spawn_bound_worker(
        bound_executable,
        bound_worker_entrypoint,
        source_fds,
        SUNOFRIEND_READY_RELEASE_TRANSPORT_COUNT
    );
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
    {
        "_spawn_bound_fake_worker_with_ready_release",
        sunofriend_spawn_bound_fake_worker_with_ready_release,
        METH_VARARGS,
        PyDoc_STR(
            "Private fixed ready/release canary boundary; production worker "
            "integration remains unavailable."
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
