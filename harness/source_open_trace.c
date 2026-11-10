#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static void denied_path(const char *operation, const char *path, int saved_errno) {
    if ((saved_errno != EACCES && saved_errno != EPERM) || path == NULL) return;
    const char *prefix = "SOURCE_DIAGNOSTIC_DENIED ";
    syscall(SYS_write, STDERR_FILENO, prefix, strlen(prefix));
    syscall(SYS_write, STDERR_FILENO, operation, strlen(operation));
    syscall(SYS_write, STDERR_FILENO, " ", 1);
    syscall(SYS_write, STDERR_FILENO, path, strnlen(path, 4096));
    syscall(SYS_write, STDERR_FILENO, "\n", 1);
}

int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        va_list arguments;
        va_start(arguments, flags);
        mode = va_arg(arguments, int);
        va_end(arguments);
    }
    int (*original)(const char *, int, ...) = dlsym(RTLD_NEXT, "open");
    int result = original(path, flags, mode);
    int saved_errno = errno;
    if (result < 0) denied_path("open", path, saved_errno);
    errno = saved_errno;
    return result;
}

int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        va_list arguments;
        va_start(arguments, flags);
        mode = va_arg(arguments, int);
        va_end(arguments);
    }
    int (*original)(const char *, int, ...) = dlsym(RTLD_NEXT, "open64");
    int result = original(path, flags, mode);
    int saved_errno = errno;
    if (result < 0) denied_path("open64", path, saved_errno);
    errno = saved_errno;
    return result;
}

int openat(int directory, const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        va_list arguments;
        va_start(arguments, flags);
        mode = va_arg(arguments, int);
        va_end(arguments);
    }
    int (*original)(int, const char *, int, ...) = dlsym(RTLD_NEXT, "openat");
    int result = original(directory, path, flags, mode);
    int saved_errno = errno;
    if (result < 0) denied_path("openat", path, saved_errno);
    errno = saved_errno;
    return result;
}

FILE *fopen(const char *path, const char *mode) {
    FILE *(*original)(const char *, const char *) = dlsym(RTLD_NEXT, "fopen");
    FILE *result = original(path, mode);
    int saved_errno = errno;
    if (result == NULL) denied_path("fopen", path, saved_errno);
    errno = saved_errno;
    return result;
}

FILE *fopen64(const char *path, const char *mode) {
    FILE *(*original)(const char *, const char *) = dlsym(RTLD_NEXT, "fopen64");
    FILE *result = original(path, mode);
    int saved_errno = errno;
    if (result == NULL) denied_path("fopen64", path, saved_errno);
    errno = saved_errno;
    return result;
}
