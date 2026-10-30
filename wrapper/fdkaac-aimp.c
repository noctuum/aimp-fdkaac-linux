/*
 * The program AIMP runs for this add-on, in place of fdkaac. AIMP starts the
 * encoders of a batch with the pipes of the other jobs inherited, installs
 * executables with mode 0777, and ignores the exit code of the encoder. The
 * wrapper closes the inherited descriptors, sets mode 0755 on itself and on
 * fdkaac, runs fdkaac from its own folder with the same arguments, and
 * removes the output when fdkaac fails, so that the converter reports an
 * error.
 */
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define BATCH 1024
#define EXIT_CANNOT_RUN 127

static void close_inherited(void)
{
    int n;
    do {
        int fds[BATCH];
        n = 0;
        DIR *d = opendir("/proc/self/fd");
        if (!d)
            return;
        struct dirent *e;
        while (n < BATCH && (e = readdir(d)) != NULL) {
            int fd = atoi(e->d_name);
            if (fd > 2 && fd != dirfd(d))
                fds[n++] = fd;
        }
        closedir(d);
        for (int i = 0; i < n; i++)
            close(fds[i]);
    } while (n == BATCH);
}

static void set_mode(const char *path)
{
    struct stat st;
    if (stat(path, &st) == 0 && (st.st_mode & 07777) != 0755)
        chmod(path, 0755);
}

static const char *output_of(int argc, char **argv)
{
    for (int i = 1; i + 1 < argc; i++)
        if (strcmp(argv[i], "-o") == 0)
            return argv[i + 1];
    return NULL;
}

int main(int argc, char **argv)
{
    close_inherited();

    char self[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", self, sizeof self - 1);
    if (len <= 0) {
        fprintf(stderr, "fdkaac-aimp: cannot read /proc/self/exe: %s\n", strerror(errno));
        return EXIT_CANNOT_RUN;
    }
    self[len] = '\0';
    const char *slash = strrchr(self, '/');
    char encoder[PATH_MAX];
    if (!slash || snprintf(encoder, sizeof encoder, "%.*s/fdkaac", (int)(slash - self), self) >= (int)sizeof encoder) {
        fprintf(stderr, "fdkaac-aimp: cannot build the path of fdkaac from %s\n", self);
        return EXIT_CANNOT_RUN;
    }
    set_mode(self);
    set_mode(encoder);

    const char *output = output_of(argc, argv);
    pid_t parent = getpid();
    pid_t child = fork();
    if (child < 0) {
        fprintf(stderr, "fdkaac-aimp: fork: %s\n", strerror(errno));
        return EXIT_CANNOT_RUN;
    }
    if (child == 0) {
        prctl(PR_SET_PDEATHSIG, SIGTERM);
        if (getppid() != parent)
            _exit(EXIT_CANNOT_RUN);
        argv[0] = encoder;
        execv(encoder, argv);
        fprintf(stderr, "fdkaac-aimp: cannot run %s: %s\n", encoder, strerror(errno));
        _exit(EXIT_CANNOT_RUN);
    }

    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) {
            fprintf(stderr, "fdkaac-aimp: waitpid: %s\n", strerror(errno));
            return EXIT_CANNOT_RUN;
        }
    }
    int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    if (code != 0 && output)
        unlink(output);
    return code;
}
