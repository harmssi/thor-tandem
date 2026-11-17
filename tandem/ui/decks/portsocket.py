"""The deck's end of a native port's socket (protocol: README, "Deck-Socket"; the game's end is ports/tandem_deck.h).

The game listens on a Unix socket and sends its state as JSON lines; the deck sends commands as text lines.
Link(path, heard, block) keeps trying to connect, calls heard(dict) for every JSON line, heard(None) when the game is
gone and, if given, block(name, bytes) for every binary block. They run on the link's own thread.
"""
import json, socket, threading, time


def split_lines(buf):
    """(what is complete in buf, the unfinished rest): a dict for every JSON line and (name, bytes) for every binary block
    ('#<name> <length>' as a line, then that many raw bytes). Any other line is skipped."""
    found, pos = [], 0
    while (end := buf.find(b'\n', pos)) >= 0:
        line = buf[pos:end]
        name, _, size = line[1:].partition(b' ')
        if line.startswith(b'#') and size.isdigit():
            if len(buf) < end + 1 + int(size): break  # the block is still on its way
            found.append((name.decode('latin-1'), buf[end + 1:end + 1 + int(size)]))
            pos = end + 1 + int(size)
            continue
        if line.startswith(b'{'):
            try: found.append(json.loads(line))
            except ValueError: pass
        pos = end + 1
    return found, buf[pos:]


class Link:
    def __init__(self, path, heard, block=None):
        self.path, self.heard, self.block, self.alive, self.sock = path, heard, block, True, None
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        while self.alive:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.path)
                self.sock, buf = sock, b''
                while self.alive:
                    chunk = sock.recv(1 << 20)
                    if not chunk: break
                    found, buf = split_lines(buf + chunk)
                    for state in found:
                        if isinstance(state, dict): self.heard(state)
                        elif self.block: self.block(*state)
            except OSError: pass
            if self.sock: self.hang_up(); self.heard(None)
            time.sleep(1)  # the game is not up yet, or gone

    def send(self, line):
        try: self.sock.sendall(line.encode() + b'\n')  # a few bytes into a local socket: does not block the painter
        except (OSError, AttributeError): pass

    def hang_up(self):
        sock, self.sock = self.sock, None
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)  # wakes the thread waiting in recv
            except OSError: pass
            sock.close()

    def close(self):
        self.alive = False
        self.hang_up()
