/*
 * The probe encoder of the probe kit. AIMP runs it as a command-line
 * encoder. It records its command line, its environment and the stream it
 * receives, and writes the audio back to OUTPUT as a WAV file.
 */
#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef PROBE_VARIANT
#define PROBE_VARIANT "unset"
#endif
#ifndef PROBE_REPORT_DIR
#define PROBE_REPORT_DIR ""
#endif

/* Room for an ID3 tag with cover art in front of the WAV header. */
#define HEAD_CAP ((size_t)64 << 20)
#define MAX_CHUNKS 32
#define EXIT_IO 74
#define EXIT_NOMEM 70

enum { NEED_MORE, IS_WAV, IS_RAW };

typedef struct {
    char *p;
    size_t len;
    size_t cap;
} sbuf;

static struct {
    int argc;
    char **argv;
    const char *id;
    const char *output;
    int exit_code;
    int discard;
    int chatter;
    char *report_stem;

    unsigned char *head;
    size_t head_len;
    size_t head_cap;
    int eof;
    int state;
    size_t id3_size;
    sbuf id3_frames;
    size_t riff_off;
    size_t riff_len;
    int have_riff_size;
    int have_wave;
    uint32_t riff_size;
    int nchunks;
    unsigned char chunk_id[MAX_CHUNKS][4];
    uint32_t chunk_size[MAX_CHUNKS];
    int have_fmt;
    size_t fmt_off;
    uint32_t fmt_size;
    size_t payload_off;
    uint64_t data_bytes;

    FILE *out;
    int out_opened;
    int out_failed;
    char *error;
    struct timespec t0;
    sbuf inherited;
} g;

static void out_of_memory(void)
{
    fputs("probe: out of memory\n", stderr);
    exit(EXIT_NOMEM);
}

static void sb_reserve(sbuf *b, size_t extra)
{
    if (b->len + extra + 1 <= b->cap)
        return;
    size_t cap = b->cap ? b->cap : 256;
    while (cap < b->len + extra + 1)
        cap *= 2;
    char *p = realloc(b->p, cap);
    if (!p)
        out_of_memory();
    b->p = p;
    b->cap = cap;
}

static void sb_add(sbuf *b, const void *s, size_t n)
{
    sb_reserve(b, n);
    memcpy(b->p + b->len, s, n);
    b->len += n;
    b->p[b->len] = '\0';
}

static void sb_str(sbuf *b, const char *s)
{
    sb_add(b, s, strlen(s));
}

__attribute__((format(printf, 2, 3)))
static void sb_fmt(sbuf *b, const char *fmt, ...)
{
    va_list ap;
    va_list copy;
    va_start(ap, fmt);
    va_copy(copy, ap);
    int n = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);
    if (n > 0) {
        sb_reserve(b, (size_t)n);
        vsnprintf(b->p + b->len, (size_t)n + 1, fmt, copy);
        b->len += (size_t)n;
    }
    va_end(copy);
}

static void sb_escaped(sbuf *b, const unsigned char *s, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        if (s[i] < 0x20 || s[i] == 0x7f || s[i] == '\\')
            sb_fmt(b, "\\x%02x", (unsigned)s[i]);
        else
            sb_add(b, s + i, 1);
    }
}

static void sb_text(sbuf *b, const char *s)
{
    sb_escaped(b, (const unsigned char *)s, strlen(s));
}

static void sb_wrapped(sbuf *b, const char *s)
{
    if (!s) {
        sb_str(b, "-");
        return;
    }
    sb_str(b, "[");
    sb_text(b, s);
    sb_str(b, "]");
}

static char *read_link(const char *path)
{
    for (size_t size = 256;; size *= 2) {
        char *buf = malloc(size);
        if (!buf)
            out_of_memory();
        ssize_t n = readlink(path, buf, size);
        if (n < 0) {
            free(buf);
            return NULL;
        }
        if ((size_t)n < size) {
            buf[n] = '\0';
            return buf;
        }
        free(buf);
    }
}

static uint16_t le16(const unsigned char *p)
{
    return (uint16_t)(p[0] | p[1] << 8);
}

static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint32_t be24(const unsigned char *p)
{
    return (uint32_t)p[0] << 16 | (uint32_t)p[1] << 8 | (uint32_t)p[2];
}

static uint32_t be32(const unsigned char *p)
{
    return (uint32_t)p[0] << 24 | be24(p + 1);
}

static uint32_t syncsafe(const unsigned char *p)
{
    return (uint32_t)(p[0] & 0x7f) << 21 | (uint32_t)(p[1] & 0x7f) << 14 |
           (uint32_t)(p[2] & 0x7f) << 7 | (uint32_t)(p[3] & 0x7f);
}

static void put_le32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)v;
    p[1] = (unsigned char)(v >> 8);
    p[2] = (unsigned char)(v >> 16);
    p[3] = (unsigned char)(v >> 24);
}

static double elapsed(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)(t.tv_sec - g.t0.tv_sec) + (double)(t.tv_nsec - g.t0.tv_nsec) / 1e9;
}

static void set_error(const char *what, const char *path)
{
    int err = errno;
    if (g.error)
        return;
    sbuf e = {NULL, 0, 0};
    sb_str(&e, what);
    if (path) {
        sb_str(&e, " ");
        sb_str(&e, path);
    }
    sb_str(&e, ": ");
    sb_str(&e, strerror(err));
    g.error = e.p;
    fprintf(stderr, "probe: %s\n", g.error);
}

/*
 * A host that starts encoders in parallel can leave each of them holding the
 * pipes of the others, and a pipe held open elsewhere never reaches end of
 * file. The probe records every descriptor above 2 it inherits and closes it.
 */
static void close_inherited(void)
{
    int fds[1024];
    int n = 0;
    DIR *d = opendir("/proc/self/fd");
    if (!d)
        return;
    struct dirent *e;
    while (n < 1024 && (e = readdir(d)) != NULL) {
        int fd = atoi(e->d_name);
        if (fd > 2 && fd != dirfd(d))
            fds[n++] = fd;
    }
    closedir(d);
    for (int i = 0; i < n; i++) {
        char link[32];
        snprintf(link, sizeof link, "/proc/self/fd/%d", fds[i]);
        char *target = read_link(link);
        sb_fmt(&g.inherited, "inherited-fd: %d ", fds[i]);
        sb_text(&g.inherited, target ? target : "?");
        sb_str(&g.inherited, "\n");
        free(target);
        close(fds[i]);
    }
}

static void read_id3_frames(const unsigned char *t, size_t size)
{
    int version = t[3];
    size_t header = version == 2 ? 6 : 10;
    size_t id_len = version == 2 ? 3 : 4;
    size_t end = size - ((t[5] & 0x10) ? 10 : 0);
    size_t p = 10;

    if ((t[5] & 0x40) && version >= 3 && p + 4 <= end)
        p += version == 4 ? syncsafe(t + p) : 4 + (size_t)be32(t + p);
    for (int count = 0; count < 64 && p + header <= end && t[p] != 0; count++) {
        size_t frame = version == 2 ? be24(t + p + 3)
                     : version == 4 ? syncsafe(t + p + 4)
                                    : be32(t + p + 4);
        if (g.id3_frames.len)
            sb_str(&g.id3_frames, " ");
        sb_escaped(&g.id3_frames, t + p, id_len);
        p += header + frame;
    }
}

static void reset_parse(void)
{
    g.id3_size = 0;
    g.id3_frames.len = 0;
    if (g.id3_frames.p)
        g.id3_frames.p[0] = '\0';
    g.riff_off = 0;
    g.riff_len = 0;
    g.have_riff_size = 0;
    g.have_wave = 0;
    g.nchunks = 0;
    g.have_fmt = 0;
}

/* Parses the buffered head of the stream from the start on every call. */
static int parse_head(int at_eof)
{
    const unsigned char *h = g.head;
    size_t n = g.head_len;
    size_t pos = 0;
    int more = at_eof ? IS_RAW : NEED_MORE;

    reset_parse();
    if (n >= 3 && memcmp(h, "ID3", 3) == 0) {
        if (n < 10)
            return more;
        size_t size = 10 + (size_t)syncsafe(h + 6) + ((h[5] & 0x10) ? 10 : 0);
        if (size > HEAD_CAP)
            return IS_RAW;
        if (n < size)
            return more;
        g.id3_size = size;
        read_id3_frames(h, size);
        pos = size;
    } else if (n < 3 && !at_eof) {
        return NEED_MORE;
    }

    g.riff_off = pos;
    g.riff_len = n - pos < 4 ? n - pos : 4;
    if (n - pos < 12)
        return more;
    if (memcmp(h + pos, "RIFF", 4) != 0 && memcmp(h + pos, "RF64", 4) != 0)
        return IS_RAW;
    g.riff_size = le32(h + pos + 4);
    g.have_riff_size = 1;
    g.have_wave = 1;
    if (memcmp(h + pos + 8, "WAVE", 4) != 0)
        return IS_RAW;

    size_t c = pos + 12;
    for (;;) {
        if (n - c < 8)
            return more;
        uint32_t size = le32(h + c + 4);
        if (g.nchunks < MAX_CHUNKS) {
            memcpy(g.chunk_id[g.nchunks], h + c, 4);
            g.chunk_size[g.nchunks] = size;
            g.nchunks++;
        }
        if (memcmp(h + c, "data", 4) == 0) {
            if (!g.have_fmt)
                return IS_RAW;
            g.payload_off = c + 8;
            return IS_WAV;
        }
        uint64_t next = (uint64_t)c + 8 + size + (size & 1);
        if (next > HEAD_CAP)
            return IS_RAW;
        if (next > n)
            return more;
        if (memcmp(h + c, "fmt ", 4) == 0 && size >= 16) {
            g.fmt_off = c + 8;
            g.fmt_size = size;
            g.have_fmt = 1;
        }
        c = (size_t)next;
    }
}

static void read_head(void)
{
    g.state = NEED_MORE;
    while (g.state == NEED_MORE) {
        if (g.head_len == g.head_cap) {
            if (g.head_cap == HEAD_CAP) {
                g.state = IS_RAW;
                break;
            }
            size_t cap = g.head_cap ? g.head_cap * 2 : (size_t)1 << 16;
            if (cap > HEAD_CAP)
                cap = HEAD_CAP;
            unsigned char *p = realloc(g.head, cap);
            if (!p)
                out_of_memory();
            g.head = p;
            g.head_cap = cap;
        }
        ssize_t r = read(STDIN_FILENO, g.head + g.head_len, g.head_cap - g.head_len);
        if (r < 0 && errno == EINTR)
            continue;
        if (r < 0)
            set_error("read stdin", NULL);
        if (r <= 0)
            g.eof = 1;
        else
            g.head_len += (size_t)r;
        g.state = parse_head(g.eof);
    }
    g.data_bytes = g.state == IS_WAV ? g.head_len - g.payload_off : g.head_len - g.id3_size;
}

static void put(const void *p, size_t n)
{
    if (!g.out || g.out_failed || n == 0)
        return;
    if (fwrite(p, 1, n, g.out) != n) {
        g.out_failed = 1;
        set_error("write", g.output);
    }
}

static void start_output(void)
{
    if (!g.out)
        return;
    if (g.state != IS_WAV) {
        put(g.head, g.head_len);
        return;
    }
    unsigned char riff[20];
    memcpy(riff, "RIFF", 4);
    put_le32(riff + 4, 0);
    memcpy(riff + 8, "WAVEfmt ", 8);
    put_le32(riff + 16, g.fmt_size);
    put(riff, sizeof riff);
    put(g.head + g.fmt_off, g.fmt_size);
    if (g.fmt_size & 1)
        put("", 1);
    unsigned char data[8];
    memcpy(data, "data", 4);
    put_le32(data + 4, 0);
    put(data, sizeof data);
    if (!g.discard)
        put(g.head + g.payload_off, g.head_len - g.payload_off);
}

static void stream_rest(void)
{
    static unsigned char buf[1 << 16];
    while (!g.eof) {
        ssize_t r = read(STDIN_FILENO, buf, sizeof buf);
        if (r < 0 && errno == EINTR)
            continue;
        if (r <= 0) {
            if (r < 0)
                set_error("read stdin", NULL);
            g.eof = 1;
            break;
        }
        g.data_bytes += (uint64_t)r;
        /* After a failed write, put() drops the data and stdin still drains, so the host never blocks on the pipe. */
        if (g.state != IS_WAV || !g.discard)
            put(buf, (size_t)r);
    }
}

static void finish_output(void)
{
    if (!g.out)
        return;
    if (g.state == IS_WAV && !g.out_failed) {
        uint64_t payload = g.discard ? 0 : g.data_bytes;
        uint64_t fmt_chunk = 8 + (uint64_t)g.fmt_size + (g.fmt_size & 1);
        uint64_t riff = 4 + fmt_chunk + 8 + payload + (payload & 1);
        unsigned char v[4];
        if (payload & 1)
            put("", 1);
        put_le32(v, riff > 0xFFFFFFFFu ? 0xFFFFFFFFu : (uint32_t)riff);
        if (fseeko(g.out, 4, SEEK_SET) == 0)
            put(v, 4);
        else
            set_error("seek", g.output);
        put_le32(v, payload > 0xFFFFFFFFu ? 0xFFFFFFFFu : (uint32_t)payload);
        if (fseeko(g.out, (off_t)(12 + fmt_chunk + 4), SEEK_SET) == 0)
            put(v, 4);
        else
            set_error("seek", g.output);
    }
    if (fclose(g.out) != 0 && !g.out_failed)
        set_error("close", g.output);
    g.out = NULL;
}

static void copy_output(void)
{
    static unsigned char buf[1 << 16];
    if (!g.report_stem || !g.out_opened || g.discard)
        return;
    FILE *in = fopen(g.output, "rb");
    if (!in)
        return;
    sbuf path = {NULL, 0, 0};
    sb_str(&path, g.report_stem);
    sb_str(&path, ".wav");
    FILE *copy = fopen(path.p, "wb");
    if (copy) {
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, in)) > 0)
            if (fwrite(buf, 1, n, copy) != n)
                break;
        fclose(copy);
    }
    fclose(in);
    free(path.p);
}

static void make_report_stem(const char *dir)
{
    const char *id = g.id ? g.id : PROBE_VARIANT;
    sbuf s = {NULL, 0, 0};
    sb_str(&s, dir);
    sb_str(&s, "/");
    for (const char *c = id; *c; c++)
        sb_add(&s, *c == '/' ? "_" : c, 1);
    sb_fmt(&s, "-%lld-%ld", (long long)time(NULL), (long)getpid());
    g.report_stem = s.p;
}

static void build_report(sbuf *b, int done)
{
    static const char *const env_names[] = {"PATH", "LD_LIBRARY_PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"};
    static const char *const fd_paths[] = {"/proc/self/fd/0", "/proc/self/fd/1", "/proc/self/fd/2"};
    const unsigned char *h = g.head;
    struct stat st;

    sb_str(b, "probe: 1\n");
    sb_fmt(b, "state: %s\n", done ? "done" : "started");
    sb_str(b, "variant: ");
    sb_text(b, PROBE_VARIANT);
    sb_str(b, "\nid: ");
    if (g.id)
        sb_text(b, g.id);
    else
        sb_str(b, "-");

    char *exe = read_link("/proc/self/exe");
    sb_str(b, "\nexe: ");
    sb_wrapped(b, exe);
    free(exe);
    sb_str(b, "\nexe-mode: ");
    if (stat("/proc/self/exe", &st) == 0)
        sb_fmt(b, "%04o", (unsigned)(st.st_mode & 07777));
    else
        sb_str(b, "-");
    sb_fmt(b, "\nuid: %u\n", (unsigned)getuid());

    char *cwd = getcwd(NULL, 0);
    sb_str(b, "cwd: ");
    sb_wrapped(b, cwd);
    free(cwd);
    sb_fmt(b, "\nargc: %d\n", g.argc);
    for (int i = 0; i < g.argc; i++) {
        sb_fmt(b, "argv[%d]: ", i);
        sb_wrapped(b, g.argv[i]);
        sb_str(b, "\n");
    }
    for (size_t i = 0; i < sizeof env_names / sizeof env_names[0]; i++) {
        sb_fmt(b, "env-%s: ", env_names[i]);
        sb_wrapped(b, getenv(env_names[i]));
        sb_str(b, "\n");
    }
    for (int fd = 0; fd < 3; fd++) {
        char *target = read_link(fd_paths[fd]);
        sb_fmt(b, "fd%d: ", fd);
        if (target)
            sb_text(b, target);
        else
            sb_str(b, "closed");
        free(target);
        sb_str(b, "\n");
    }
    if (g.inherited.len)
        sb_add(b, g.inherited.p, g.inherited.len);
    else
        sb_str(b, "inherited-fd: -\n");

    sb_str(b, "output: ");
    sb_wrapped(b, g.output);
    sb_fmt(b, "\nid3-size: %zu\nid3-frames: ", g.id3_size);
    if (g.id3_frames.len)
        sb_str(b, g.id3_frames.p);
    else
        sb_str(b, "-");
    sb_str(b, "\nriff: ");
    if (g.riff_len)
        sb_escaped(b, h + g.riff_off, g.riff_len);
    else
        sb_str(b, "-");
    sb_str(b, "\nriff-size: ");
    if (g.have_riff_size)
        sb_fmt(b, "%u", (unsigned)g.riff_size);
    else
        sb_str(b, "-");
    sb_str(b, "\nwave: ");
    if (g.have_wave)
        sb_escaped(b, h + g.riff_off + 8, 4);
    else
        sb_str(b, "-");
    sb_str(b, "\n");
    for (int i = 0; i < g.nchunks; i++) {
        sb_str(b, "chunk: ");
        sb_escaped(b, g.chunk_id[i], 4);
        sb_fmt(b, " %u\n", (unsigned)g.chunk_size[i]);
    }

    if (g.have_fmt) {
        const unsigned char *f = h + g.fmt_off;
        unsigned tag = le16(f);
        sb_fmt(b, "format-tag: 0x%04X\nchannels: %u\nsample-rate: %u\nbyte-rate: %u\nblock-align: %u\nbits: %u\n",
               tag, (unsigned)le16(f + 2), (unsigned)le32(f + 4), (unsigned)le32(f + 8),
               (unsigned)le16(f + 12), (unsigned)le16(f + 14));
        if (tag == 0xFFFE && g.fmt_size >= 40) {
            const unsigned char *s = f + 24;
            sb_fmt(b, "valid-bits: %u\nchannel-mask: 0x%08X\n", (unsigned)le16(f + 18), (unsigned)le32(f + 20));
            sb_fmt(b, "subformat: %08x-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x\n",
                   (unsigned)le32(s), (unsigned)le16(s + 4), (unsigned)le16(s + 6),
                   s[8], s[9], s[10], s[11], s[12], s[13], s[14], s[15]);
        } else {
            sb_str(b, "valid-bits: -\nchannel-mask: -\nsubformat: -\n");
        }
    } else {
        sb_str(b, "format-tag: -\nchannels: -\nsample-rate: -\nbyte-rate: -\nblock-align: -\nbits: -\n"
                  "valid-bits: -\nchannel-mask: -\nsubformat: -\n");
    }

    sb_str(b, "header-hex: ");
    if (g.state == IS_WAV) {
        for (size_t i = g.riff_off; i < g.payload_off; i++)
            sb_fmt(b, "%02x", h[i]);
    } else {
        sb_str(b, "-");
    }
    sb_fmt(b, "\ndata-bytes: %llu\nseconds: %.3f\n", (unsigned long long)g.data_bytes, elapsed());
    if (done)
        sb_fmt(b, "exit: %d\n", g.error ? EXIT_IO : g.exit_code);
    else
        sb_str(b, "exit: -\n");
    if (g.error) {
        sb_str(b, "error: ");
        sb_text(b, g.error);
        sb_str(b, "\n");
    }
}

static int write_file(const char *path, const sbuf *b)
{
    FILE *f = fopen(path, "wb");
    if (!f)
        return 0;
    int ok = fwrite(b->p, 1, b->len, f) == b->len;
    return fclose(f) == 0 && ok;
}

static void write_report(int done)
{
    sbuf b = {NULL, 0, 0};
    build_report(&b, done);
    if (g.output) {
        sbuf path = {NULL, 0, 0};
        sb_str(&path, g.output);
        sb_str(&path, ".probe.txt");
        write_file(path.p, &b);
        free(path.p);
    }
    if (g.report_stem) {
        sbuf path = {NULL, 0, 0};
        sb_str(&path, g.report_stem);
        sb_str(&path, ".txt");
        write_file(path.p, &b);
        free(path.p);
    }
    free(b.p);
}

int main(int argc, char **argv)
{
    close_inherited();
    signal(SIGPIPE, SIG_IGN);
    clock_gettime(CLOCK_MONOTONIC, &g.t0);
    g.argc = argc;
    g.argv = argv;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--id") == 0 && i + 1 < argc)
            g.id = argv[++i];
        else if (strcmp(argv[i], "--exit") == 0 && i + 1 < argc)
            g.exit_code = (int)strtol(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--discard") == 0)
            g.discard = 1;
        else if (strcmp(argv[i], "--chatter") == 0)
            g.chatter = 1;
        else if (strcmp(argv[i], "-o") == 0 && i + 1 < argc && !g.output)
            g.output = argv[++i];
    }

    const char *dir = getenv("PROBE_REPORT_DIR");
    if (!dir)
        dir = PROBE_REPORT_DIR;
    if (*dir)
        make_report_stem(dir);

    if (g.chatter) {
        for (int i = 1; i <= 3; i++) {
            printf("probe: stdout line %d\n", i);
            fprintf(stderr, "probe: stderr line %d\n", i);
        }
        fflush(stdout);
    }

    if (g.output) {
        g.out = fopen(g.output, "wb");
        if (g.out)
            g.out_opened = 1;
        else
            set_error("open", g.output);
    }

    read_head();
    start_output();
    write_report(0);
    stream_rest();
    finish_output();
    copy_output();
    write_report(1);
    return g.error ? EXIT_IO : g.exit_code;
}
