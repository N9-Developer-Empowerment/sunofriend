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
#include <unistd.h>

/*
 * SOURCE-ONLY SECURITY BOUNDARY
 *
 * This private CPython extension is deliberately shipped as uncompiled source.
 * It is not registered with setuptools, imported by Python, or reachable from
 * a Sunofriend command. A later increment may compile and expose it only after
 * build provenance, executable identity, lifecycle, and live-authority gates
 * have their own review.
 *
 * The future entry point accepts three already-open parent descriptors. It
 * changes no parent descriptor flag or table entry. All descriptor changes
 * below are ordered posix_spawn child file actions.
 */

#ifndef POSIX_SPAWN_CLOEXEC_DEFAULT
#error "The audited Darwin POSIX_SPAWN_CLOEXEC_DEFAULT flag is required."
#endif

#define SUNOFRIEND_SCRATCH_FD_MIN 6

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
                || (status_flags & (O_APPEND | O_NONBLOCK)) != 0
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
        disposition.sa_handler == SIG_IGN
        || (disposition.sa_flags & SA_NOCLDWAIT) != 0
    ) {
        PyErr_SetString(
            PyExc_ValueError,
            "parent SIGCHLD disposition cannot preserve an owned child"
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
sunofriend_reap_after_result_allocation_failure(pid_t child_pid)
{
    int wait_status;
    int group_kill_status;
    pid_t waited;

    /*
     * POSIX_SPAWN_SETPGROUP with pgroup 0 makes child_pid the exact new group.
     * Terminate that owned group, then reap the exact child without replacing
     * the Python allocation exception.
     */
    group_kill_status = kill(-child_pid, SIGKILL);
    if (group_kill_status != 0 && errno != ESRCH) {
        (void)kill(child_pid, SIGKILL);
    }
    for (;;) {
        waited = waitpid(child_pid, &wait_status, 0);
        if (waited < 0 && errno == EINTR) {
            continue;
        }
        if (waited == child_pid || (waited < 0 && errno == ECHILD)) {
            return;
        }
        /*
         * EINTR is expected. Any other error is retried because returning here
         * could knowingly discard ownership of a live PID after allocation
         * failure. This emergency path therefore fails closed.
         */
    }
}

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

    (void)posix_spawnattr_destroy(&attributes);
    (void)posix_spawn_file_actions_destroy(&file_actions);
    {
        PyObject *result = PyLong_FromLong((long)child_pid);
        if (result == NULL) {
            sunofriend_reap_after_result_allocation_failure(child_pid);
        }
        return result;
    }

fail:
    if (attributes_ready) {
        (void)posix_spawnattr_destroy(&attributes);
    }
    if (file_actions_ready) {
        (void)posix_spawn_file_actions_destroy(&file_actions);
    }
    return sunofriend_raise_spawn_error(status, failed_operation);
}

static PyMethodDef sunofriend_spawn_methods[] = {
    {
        "_spawn_bound_fake_worker",
        sunofriend_spawn_bound_fake_worker,
        METH_VARARGS,
        PyDoc_STR(
            "Private future boundary; unavailable until a separately audited "
            "build and runtime integration exists."
        ),
    },
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef sunofriend_spawn_module = {
    PyModuleDef_HEAD_INIT,
    "_separation_native_spawn_darwin",
    "Private source-only Darwin spawn boundary.",
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
    return PyModule_Create(&sunofriend_spawn_module);
}
