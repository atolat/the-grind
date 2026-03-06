"""
select() vs epoll/kqueue: Understanding I/O Multiplexing
=========================================================

This program demonstrates the TWO ways an event loop can watch multiple
network connections for incoming data.

Run this file directly:
    python 04a-select-vs-epoll.py

It will:
1. Start a server using select() — the old way
2. Start a server using selectors (epoll/kqueue) — the modern way
3. Spawn clients that connect to both and send messages
4. Print what's happening at each step so you can see the difference

Key concepts:
- A "socket" is an OS-level handle for a network connection
- When data arrives on a socket, someone needs to notice
- select() and epoll/kqueue are two different strategies for noticing
"""

import select
import selectors
import socket
import threading
import time

# =============================================================================
# HELPER: Create a simple TCP server socket
# =============================================================================

def make_server_socket(port: int) -> socket.socket:
    """
    Create a TCP server socket that listens on the given port.

    Steps:
    1. socket()  — Ask the OS to create a network endpoint
    2. setsockopt() — Allow reusing the port if we restart quickly
    3. bind()    — Attach the socket to a specific port
    4. listen()  — Tell the OS "I'm ready to accept connections"
    5. setblocking(False) — NON-BLOCKING mode!
       This is crucial: recv() will return immediately (with EAGAIN)
       instead of blocking the thread when no data is available.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(10)
    server.setblocking(False)  # <-- THIS IS THE KEY for async I/O
    return server


# =============================================================================
# SERVER 1: Using select() — The Old Way
# =============================================================================

def run_select_server(port: int, duration: float = 5.0):
    """
    A server that uses select.select() to watch multiple sockets.

    How select() works:
    -------------------
    You pass it THREE lists of sockets:
      - readable: "tell me when any of these have data to read"
      - writable: "tell me when any of these are ready to write"
      - exceptional: "tell me if any of these have errors"

    select() then BLOCKS until at least one socket in any list is ready.

    THE PROBLEM:
    Every single call to select(), the OS kernel must:
    1. Copy your entire list of sockets from user space → kernel space
    2. Walk through EVERY socket in the list and check its status
    3. Copy the results back to user space

    With 10,000 sockets, that's 10,000 checks PER CALL.
    And you call select() in a loop, so it's O(n) on EVERY iteration.
    """
    server = make_server_socket(port)
    print(f"[SELECT server] Listening on port {port}")

    # This list holds ALL sockets we're watching.
    # It starts with just the server socket (for new connections).
    # As clients connect, we add their sockets too.
    all_sockets: list[socket.socket] = [server]

    start = time.time()
    total_select_calls = 0
    total_sockets_checked = 0

    while time.time() - start < duration:
        # ─── THE SELECT CALL ───────────────────────────────────────
        # This is where the "scanning all sockets" happens.
        #
        # Arguments:
        #   all_sockets  — check these for readability
        #   []           — we don't care about writability right now
        #   []           — we don't care about errors right now
        #   0.1          — timeout: wait at most 0.1 seconds
        #
        # Returns:
        #   readable — the subset of all_sockets that have data
        #
        # INTERNALLY: The OS copies all_sockets to kernel space,
        # scans EVERY one, returns the ready ones.
        # Even if only 1 out of 10,000 is ready, it checks all 10,000.
        # ───────────────────────────────────────────────────────────

        readable, _, _ = select.select(all_sockets, [], [], 0.1)
        total_select_calls += 1
        total_sockets_checked += len(all_sockets)  # OS checks ALL of them

        for sock in readable:
            if sock is server:
                # ─── New client connecting ─────────────────────────
                # accept() returns a NEW socket for this specific client.
                # We add it to our watch list so select() checks it too.
                client, addr = server.accept()
                client.setblocking(False)
                all_sockets.append(client)
                print(f"  [SELECT] New connection from {addr}. "
                      f"Now watching {len(all_sockets)} sockets.")
            else:
                # ─── Existing client sent data ─────────────────────
                try:
                    data = sock.recv(1024)
                    if data:
                        msg = data.decode().strip()
                        print(f"  [SELECT] Received: {msg!r}")
                        sock.sendall(f"echo: {msg}\n".encode())
                    else:
                        # Empty data = client disconnected
                        print(f"  [SELECT] Client disconnected.")
                        all_sockets.remove(sock)
                        sock.close()
                except (ConnectionResetError, BrokenPipeError):
                    all_sockets.remove(sock)
                    sock.close()

    # Cleanup
    for sock in all_sockets:
        sock.close()

    print(f"\n[SELECT server] Stats:")
    print(f"  select() called {total_select_calls} times")
    print(f"  Total sockets scanned across all calls: {total_sockets_checked}")
    print(f"  (Every call scans ALL sockets, even idle ones)\n")


# =============================================================================
# SERVER 2: Using selectors — The Modern Way (epoll/kqueue under the hood)
# =============================================================================

def run_selectors_server(port: int, duration: float = 5.0):
    """
    A server that uses the selectors module (epoll on Linux, kqueue on macOS).

    How epoll/kqueue works:
    -----------------------
    Instead of passing a list every time, you:
    1. Create a persistent watch list in the kernel (ONCE)
    2. Register sockets to it (add/remove as needed)
    3. Ask "what's ready?" — kernel already knows, returns INSTANTLY

    THE KEY DIFFERENCE:
    - select():    "Here are 10,000 sockets. Check all of them."  (every time)
    - epoll():     "Anything ready?"  "Yes, socket 47."           (O(1) per event)

    The kernel knows because the network card triggered a HARDWARE INTERRUPT
    when data arrived. The kernel flagged that socket. No scanning needed.

    Python's selectors.DefaultSelector automatically picks the best available:
    - Linux:   selectors.EpollSelector (uses epoll)
    - macOS:   selectors.KqueueSelector (uses kqueue)
    - Windows: selectors.SelectSelector (falls back to select — Windows has no epoll)
    """
    server = make_server_socket(port)
    print(f"[SELECTOR server] Listening on port {port}")

    # ─── Create the selector ──────────────────────────────────────
    # This creates the kernel-level watch list.
    # On Linux: calls epoll_create() system call
    # On macOS: calls kqueue() system call
    # ──────────────────────────────────────────────────────────────
    sel = selectors.DefaultSelector()
    print(f"  Using: {type(sel).__name__}")
    # e.g., "KqueueSelector" on macOS, "EpollSelector" on Linux

    # ─── Register the server socket ───────────────────────────────
    # This tells the kernel: "Add this socket to your watch list.
    # Notify me when it's readable (EVENT_READ = new client connecting)."
    #
    # On Linux: calls epoll_ctl(EPOLL_CTL_ADD, server_fd, EPOLLIN)
    # On macOS: calls kevent() with EV_ADD flag
    #
    # This is done ONCE per socket. Not every loop iteration.
    # ──────────────────────────────────────────────────────────────
    sel.register(server, selectors.EVENT_READ, data="server")

    start = time.time()
    total_select_calls = 0
    registered_count = 1  # Just the server socket initially

    while time.time() - start < duration:
        # ─── THE SELECT CALL ───────────────────────────────────────
        # Ask the kernel: "Any sockets ready?"
        #
        # On Linux:  calls epoll_wait() — returns only the READY sockets
        # On macOS:  calls kevent() — returns only the READY events
        #
        # CRUCIAL DIFFERENCE FROM select():
        #   - Does NOT copy a socket list to kernel (it's already there)
        #   - Does NOT scan all sockets (kernel already flagged the ready ones)
        #   - Returns ONLY the ready sockets, not "here's your list back"
        #   - O(number of ready sockets), NOT O(total sockets)
        #
        # If you have 10,000 sockets and only 3 are ready:
        #   select():    scans 10,000, returns 3    → O(10,000)
        #   epoll_wait(): returns 3 immediately      → O(3)
        # ───────────────────────────────────────────────────────────

        events = sel.select(timeout=0.1)
        total_select_calls += 1

        for selector_key, event_mask in events:
            if selector_key.data == "server":
                # ─── New client connecting ─────────────────────────
                client, addr = server.accept()
                client.setblocking(False)

                # Register the new client socket with the kernel.
                # On Linux: epoll_ctl(EPOLL_CTL_ADD, client_fd, EPOLLIN)
                # Done ONCE for this client. Kernel remembers it.
                sel.register(client, selectors.EVENT_READ, data=addr)
                registered_count += 1
                print(f"  [SELECTOR] New connection from {addr}. "
                      f"Registered {registered_count} sockets with kernel.")
            else:
                # ─── Existing client sent data ─────────────────────
                sock = selector_key.fileobj
                try:
                    data = sock.recv(1024)
                    if data:
                        msg = data.decode().strip()
                        print(f"  [SELECTOR] Received: {msg!r}")
                        sock.sendall(f"echo: {msg}\n".encode())
                    else:
                        # Client disconnected — remove from kernel watch list.
                        # On Linux: epoll_ctl(EPOLL_CTL_DEL, client_fd)
                        print(f"  [SELECTOR] Client disconnected.")
                        sel.unregister(sock)
                        registered_count -= 1
                        sock.close()
                except (ConnectionResetError, BrokenPipeError):
                    sel.unregister(sock)
                    registered_count -= 1
                    sock.close()

    # Cleanup
    sel.close()
    server.close()

    print(f"\n[SELECTOR server] Stats:")
    print(f"  select()/epoll_wait()/kevent() called {total_select_calls} times")
    print(f"  Kernel maintained the watch list — no scanning needed")
    print(f"  (Only ready sockets returned, not all of them)\n")


# =============================================================================
# TEST CLIENT: Spawns multiple connections and sends messages
# =============================================================================

def run_test_clients(port: int, num_clients: int = 5, server_label: str = ""):
    """
    Spawn multiple clients that connect and send a message.
    This simulates concurrent connections hitting the server.
    """
    time.sleep(0.5)  # Let the server start up

    def client_task(client_id: int):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", port))
            msg = f"Hello from client {client_id} to {server_label}"
            sock.sendall(f"{msg}\n".encode())
            response = sock.recv(1024)
            time.sleep(1)  # Hold connection open briefly
            sock.close()
        except ConnectionRefusedError:
            print(f"  Client {client_id}: connection refused")

    threads = [
        threading.Thread(target=client_task, args=(i,))
        for i in range(num_clients)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# =============================================================================
# MAIN: Run both servers and compare
# =============================================================================

def main():
    print("=" * 70)
    print("I/O MULTIPLEXING DEMO: select() vs epoll/kqueue")
    print("=" * 70)

    print("\n📋 What to watch for:")
    print("  - SELECT server: scans ALL sockets on every call")
    print("  - SELECTOR server: kernel only returns READY sockets")
    print("  - Both do the same job. The difference is efficiency at scale.\n")

    # --- Test 1: select() server ---
    print("-" * 70)
    print("TEST 1: Server using select()")
    print("-" * 70)
    server_thread = threading.Thread(
        target=run_select_server, args=(9001, 4.0)
    )
    server_thread.start()
    run_test_clients(9001, num_clients=5, server_label="SELECT")
    server_thread.join()

    time.sleep(0.5)

    # --- Test 2: selectors (epoll/kqueue) server ---
    print("-" * 70)
    print("TEST 2: Server using selectors (epoll/kqueue)")
    print("-" * 70)
    server_thread = threading.Thread(
        target=run_selectors_server, args=(9002, 4.0)
    )
    server_thread.start()
    run_test_clients(9002, num_clients=5, server_label="SELECTOR")
    server_thread.join()

    # --- Summary ---
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
    select():
      ✗ Copies socket list to kernel EVERY call
      ✗ Kernel scans ALL sockets, even idle ones
      ✗ O(total sockets) per call
      ✗ Limit: typically 1024 sockets max (FD_SETSIZE)

    epoll/kqueue (via selectors):
      ✓ Socket list lives in kernel (registered once)
      ✓ Kernel only returns READY sockets (flagged by hardware interrupts)
      ✓ O(ready sockets) per call
      ✓ No practical limit on number of sockets

    At 5 connections, both are fine.
    At 10,000+ connections, select() becomes a bottleneck.
    That's why nginx, Node.js, Redis, asyncio all use epoll/kqueue.
    """)


if __name__ == "__main__":
    main()
