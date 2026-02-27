/*
Connection Pool using a Bounded Queue (Go channels)
=====================================================

WHY CONNECTION POOLING?
    Same reason as Python: avoid the cost of opening a new DB connection
    for every query. Keep a fixed set of connections in a queue and reuse them.

DATA STRUCTURE: Go Channel (chan)
    - A Go channel IS a thread-safe bounded queue, built into the language.
    - `make(chan *Conn, size)` creates a buffered channel that holds `size` items.
    - Sending to a full channel blocks. Receiving from an empty channel blocks.
    - This blocking behaviour is exactly what we need for a connection pool.

GO CONCEPTS USED (read these if you're new to Go):
    - struct      : like a Python class, but no inheritance. Just fields + methods.
    - method      : a function attached to a struct via a "receiver" (p *Pool).
    - goroutine   : `go func()` launches a lightweight thread (like threading.Thread).
    - channel     : `chan T` is a typed, thread-safe queue for passing data between goroutines.
    - sync.WaitGroup : a counter that lets you wait for N goroutines to finish (like joining threads).
    - defer       : schedules a function call to run when the current function exits (like `finally`).
    - error       : Go doesn't have exceptions. Functions return an error value you must check.
*/

package main

import (
	"fmt"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Fake DB connection (stand-in until we wire up a real database)
// ---------------------------------------------------------------------------

// Conn simulates a database connection.
// In Go, a struct groups related data (like a Python class with only __init__ fields).
type Conn struct {
	ID     int
	Closed bool
}

// Global counter for assigning connection IDs.
// In production code you'd use atomic counters; this is fine for a demo.
var connCounter int

// NewConn creates a fake connection (factory function — Go convention for constructors).
func NewConn() *Conn {
	connCounter++
	c := &Conn{ID: connCounter} // &Conn{} allocates a Conn and returns a pointer to it
	fmt.Printf("  [conn-%d] opened\n", c.ID)
	return c
}

// Execute pretends to run a SQL query.
// This is a METHOD on Conn — `(c *Conn)` is the receiver (like `self` in Python).
func (c *Conn) Execute(sql string) string {
	if c.Closed {
		panic(fmt.Sprintf("conn-%d is closed", c.ID))
	}
	fmt.Printf("  [conn-%d] executing: %s\n", c.ID, sql)
	time.Sleep(100 * time.Millisecond) // simulate query latency
	return fmt.Sprintf("result from conn-%d", c.ID)
}

// Close marks the connection as closed.
func (c *Conn) Close() {
	c.Closed = true
	fmt.Printf("  [conn-%d] closed\n", c.ID)
}

// ---------------------------------------------------------------------------
// Connection Pool
// ---------------------------------------------------------------------------

// Pool holds a fixed number of connections in a buffered channel.
type Pool struct {
	conns    chan *Conn // The bounded queue. This IS the pool.
	poolSize int
}

// NewPool creates a pool and pre-fills it with ready connections.
func NewPool(size int) *Pool {
	p := &Pool{
		// make(chan *Conn, size) creates a buffered channel.
		// It can hold up to `size` items before blocking.
		conns:    make(chan *Conn, size),
		poolSize: size,
	}

	// Pre-fill: create connections and push them into the channel.
	for i := 0; i < size; i++ {
		p.conns <- NewConn() // <- sends a value into the channel
	}

	return p
}

// Get borrows a connection from the pool.
//
// `<-p.conns` receives from the channel.
// If the channel is empty (all connections in use), this BLOCKS until
// another goroutine returns a connection — just like queue.Queue.get() in Python.
//
// We add a timeout using `select` + `time.After` so callers don't wait forever.
func (p *Pool) Get() (*Conn, error) {
	// `select` waits on multiple channel operations, whichever is ready first wins.
	select {
	case conn := <-p.conns: // got a connection
		fmt.Printf("  [pool] handed out conn-%d  (available: %d/%d)\n",
			conn.ID, len(p.conns), p.poolSize)
		return conn, nil

	case <-time.After(5 * time.Second): // timeout
		return nil, fmt.Errorf("no connection available within 5s (pool size: %d)", p.poolSize)
	}
}

// Release returns a connection back to the pool.
// `p.conns <- conn` sends the connection back into the channel.
func (p *Pool) Release(conn *Conn) {
	p.conns <- conn
	fmt.Printf("  [pool] returned  conn-%d  (available: %d/%d)\n",
		conn.ID, len(p.conns), p.poolSize)
}

// Close drains the pool and closes every connection.
func (p *Pool) Close() {
	close(p.conns) // closing the channel lets us range over remaining items
	for conn := range p.conns {
		conn.Close()
	}
	fmt.Println("  [pool] all connections closed")
}

// ---------------------------------------------------------------------------
// Demo: multiple goroutines sharing a small pool
// ---------------------------------------------------------------------------

func worker(pool *Pool, workerID int, wg *sync.WaitGroup) {
	// `defer` schedules wg.Done() to run when this function exits.
	// This is like Python's `finally` — it runs no matter what.
	defer wg.Done()

	fmt.Printf("Worker-%d: waiting for a connection...\n", workerID)

	conn, err := pool.Get()
	if err != nil {
		fmt.Printf("Worker-%d: error: %v\n", workerID, err)
		return
	}

	// Use the connection.
	result := conn.Execute(fmt.Sprintf("SELECT * FROM users  -- worker %d", workerID))
	fmt.Printf("Worker-%d: got %s\n", workerID, result)

	// ALWAYS return the connection (defer in real code).
	pool.Release(conn)
}

func main() {
	poolSize := 2
	numWorkers := 5

	fmt.Printf("=== Creating pool with %d connections ===\n\n", poolSize)
	pool := NewPool(poolSize)

	fmt.Printf("\n=== Launching %d workers (only %d can run at once) ===\n\n", numWorkers, poolSize)

	// sync.WaitGroup is a counter:
	//   wg.Add(n) — "I'm launching n goroutines"
	//   wg.Done() — "one goroutine finished" (decrements counter)
	//   wg.Wait() — "block until counter hits 0" (like thread.join())
	var wg sync.WaitGroup
	wg.Add(numWorkers)

	for i := 0; i < numWorkers; i++ {
		// `go` launches a goroutine (lightweight thread).
		// Like Python's threading.Thread(target=worker).start(), but much cheaper.
		go worker(pool, i, &wg)
	}

	// Wait for all workers to finish.
	wg.Wait()

	fmt.Printf("\n=== Shutting down pool ===\n\n")
	pool.Close()
}
