package service

import (
	"context"
	"sync"
	"testing"
)

func isDone(ch chan struct{}) bool {
	select {
	case <-ch:
		return true
	default:
		return false
	}
}

func newTestHub() *Hub {
	return &Hub{
		clients:      make(map[int64]*ClientConnection),
		aiAgentConns: make(map[int64]*AiAgentConn),
	}
}

func newTestClient(h *Hub, userID int64) *ClientConnection {
	return newClientConnection(h, nil, userID)
}

// TestUnregisterStaleConnectionDoesNotKillNewConnection 复现 review 发现的重连竞态：
// 旧连接退出时，Unregister 不得移除/关闭当前注册的新连接。
func TestUnregisterStaleConnectionDoesNotKillNewConnection(t *testing.T) {
	h := newTestHub()

	oldConn := newTestClient(h, 5)
	newConn := newTestClient(h, 5)

	h.Register(oldConn)
	h.Register(newConn)

	// Register 替换旧连接时，旧连接应被关闭，新连接保持存活
	if !isDone(oldConn.done) {
		t.Fatal("old connection should be closed after being replaced by Register")
	}
	if isDone(newConn.done) {
		t.Fatal("new connection should not be closed after Register replaces old one")
	}

	// 模拟旧连接 readPump 退出 → 调用 Unregister(oldConn)
	h.Unregister(oldConn)

	// 新连接必须仍然注册且存活
	h.mu.RLock()
	cur, ok := h.clients[5]
	h.mu.RUnlock()
	if !ok || cur != newConn {
		t.Fatal("new connection was removed from clients map by stale unregister")
	}
	if isDone(newConn.done) {
		t.Fatal("new connection was closed by stale unregister")
	}
}

// TestUnregisterCurrentConnectionRemovesAndCloses 验证真正断开连接时 Unregister 正常清理。
func TestUnregisterCurrentConnectionRemovesAndCloses(t *testing.T) {
	h := newTestHub()

	conn := newTestClient(h, 5)
	h.Register(conn)

	h.Unregister(conn)

	h.mu.RLock()
	_, ok := h.clients[5]
	h.mu.RUnlock()
	if ok {
		t.Fatal("current connection should be removed from clients map on unregister")
	}
	if !isDone(conn.done) {
		t.Fatal("current connection should be closed on unregister")
	}
}

// TestUnregisterOnlyCancelsOwnersStreams 验证 Unregister 只取消该用户自己的 aiagent 流，
// 且被替换的旧连接退出不会取消该用户当前仍活跃的流。
func TestUnregisterOnlyCancelsOwnersStreams(t *testing.T) {
	h := newTestHub()

	user5old := newTestClient(h, 5)
	user5new := newTestClient(h, 5)
	user6 := newTestClient(h, 6)
	h.Register(user5old)
	h.Register(user5new) // 替换 user5old → user5old 成为旧连接
	h.Register(user6)

	ctx5, cancel5 := context.WithCancel(context.Background())
	ctx6, cancel6 := context.WithCancel(context.Background())
	_ = ctx5
	_ = ctx6
	h.mu.Lock()
	h.aiAgentConns[100] = &AiAgentConn{ConversationID: 100, UserID: 5, Cancel: cancel5}
	h.aiAgentConns[200] = &AiAgentConn{ConversationID: 200, UserID: 6, Cancel: cancel6}
	h.mu.Unlock()

	// 旧连接（被替换）退出：不得取消用户 5 的流
	h.Unregister(user5old)

	h.mu.RLock()
	_, ok5 := h.aiAgentConns[100]
	_, ok6 := h.aiAgentConns[200]
	h.mu.RUnlock()
	if !ok5 {
		t.Fatal("stale unregister cancelled the user's still-active stream")
	}
	if !ok6 {
		t.Fatal("unregister of user5 cancelled user6's stream")
	}

	// 当前连接退出：应取消用户 5 的流，但保留用户 6 的
	h.Unregister(user5new)
	h.mu.RLock()
	_, ok5 = h.aiAgentConns[100]
	_, ok6 = h.aiAgentConns[200]
	h.mu.RUnlock()
	if ok5 {
		t.Fatal("current unregister should cancel the user's own stream")
	}
	if !ok6 {
		t.Fatal("current unregister cancelled user6's stream")
	}
}

// TestRegisterReplaceClosesOldExactlyOnce 验证替换旧连接时 old.Close 只触发一次（sync.Once）。
func TestRegisterReplaceClosesOldExactlyOnce(t *testing.T) {
	h := newTestHub()

	conn := newTestClient(h, 5)
	h.Register(conn)
	h.Register(conn) // 同实例重复注册（幂等替换）

	// 同一实例再次注册自己：不应 panic，且 done 已关闭
	if !isDone(conn.done) {
		t.Fatal("connection should be closed after being replaced by itself")
	}

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			h.Unregister(conn)
		}()
	}
	wg.Wait()
	// 并发 Unregister 不应 panic（Close 由 sync.Once 保护）
}
