package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	waLog "go.mau.fi/whatsmeow/util/log"
)

func TestShouldForward(t *testing.T) {
	cases := []struct {
		jid     string
		watched bool
		want    bool
	}{
		{"27821234567@s.whatsapp.net", false, true},
		{"1234@lid", false, true},
		{"123-456@g.us", false, false},
		{"123-456@g.us", true, true},
	}
	for _, c := range cases {
		if got := shouldForward(c.jid, c.watched); got != c.want {
			t.Errorf("shouldForward(%q, %v) = %v, want %v", c.jid, c.watched, got, c.want)
		}
	}
}

func TestMessagesAfter(t *testing.T) {
	// NewMessageStore uses the relative "store" dir, so run inside a temp dir.
	t.Chdir(t.TempDir())
	store, err := NewMessageStore()
	if err != nil {
		t.Fatal(err)
	}
	defer store.db.Close()

	t1 := time.Date(2026, 10, 18, 10, 0, 0, 0, time.UTC)
	t2 := t1.Add(time.Minute)
	t3 := t2.Add(time.Minute)
	direct := "27821234567@s.whatsapp.net"
	group := "123-456@g.us"
	for _, c := range []struct{ jid, name string }{{direct, "Anna"}, {group, "Group"}} {
		if _, err := store.db.Exec("INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)", c.jid, c.name, t3); err != nil {
			t.Fatal(err)
		}
	}
	add := func(id, jid, content string, ts time.Time, fromMe bool) {
		t.Helper()
		if err := store.StoreMessage(id, jid, "27821234567", content, ts, fromMe, "", "", "", nil, nil, nil, 0, "", "", ""); err != nil {
			t.Fatal(err)
		}
	}
	add("m1", direct, "one", t1, false)
	add("m2", direct, "two", t2, true)
	add("m3", direct, "three", t3, false)
	add("g1", group, "group msg", t3, false)

	got, err := store.MessagesAfter(t1, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 {
		t.Fatalf("got %d messages, want 2: %+v", len(got), got)
	}
	if got[0].Message.ID != "m2" || got[1].Message.ID != "m3" {
		t.Errorf("wrong order/ids: %q, %q", got[0].Message.ID, got[1].Message.ID)
	}
	if got[0].Event != "message" || got[0].Chat.JID != direct || got[0].Chat.Name != "Anna" ||
		got[0].Message.Content != "two" || !got[0].Message.IsFromMe {
		t.Errorf("unexpected first payload: %+v", got[0])
	}

	got, err = store.MessagesAfter(t1, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].Message.ID != "m2" {
		t.Errorf("limit=1: got %+v, want only m2", got)
	}
}

func TestMessagesAfterMixedOffsets(t *testing.T) {
	t.Chdir(t.TempDir())
	store, err := NewMessageStore()
	if err != nil {
		t.Fatal(err)
	}
	defer store.db.Close()

	direct := "27821234567@s.whatsapp.net"
	if _, err := store.db.Exec("INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)", direct, "Anna", time.Now()); err != nil {
		t.Fatal(err)
	}
	plus2 := time.FixedZone("x", 2*3600)
	// Stored in +02:00: 11:30+02 = 09:30Z (before after), 12:30+02 = 10:30Z, 13:00+02 = 11:00Z.
	for _, m := range []struct {
		id string
		ts time.Time
	}{
		{"early", time.Date(2026, 10, 18, 11, 30, 0, 0, plus2)},
		{"b", time.Date(2026, 10, 18, 12, 30, 0, 0, plus2)},
		{"c", time.Date(2026, 10, 18, 13, 0, 0, 0, plus2)},
	} {
		if err := store.StoreMessage(m.id, direct, "27821234567", m.id, m.ts, false, "", "", "", nil, nil, nil, 0, "", "", ""); err != nil {
			t.Fatal(err)
		}
	}

	after := time.Date(2026, 10, 18, 10, 0, 0, 0, time.UTC)
	got, err := store.MessagesAfter(after, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0].Message.ID != "b" || got[1].Message.ID != "c" {
		t.Errorf("got %+v, want [b c]", got)
	}
}

func TestWebhookCarriesMessageTime(t *testing.T) {
	got := make(chan WebhookPayload, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var p WebhookPayload
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
			t.Errorf("decode webhook body: %v", err)
		}
		got <- p
	}))
	defer srv.Close()
	t.Setenv("WHATSAPP_WEBHOOK_URL", srv.URL)

	sent := time.Date(2026, 10, 19, 6, 30, 0, 0, time.UTC)
	sendWebhookNotification("27820000000@s.whatsapp.net", "Anna", "M1", "27820000000", "hallo", false, "", "", sent, waLog.Noop)
	select {
	case p := <-got:
		if !p.Timestamp.Equal(sent) {
			t.Fatalf("timestamp = %v, want the message time %v", p.Timestamp, sent)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("no webhook request")
	}
}

func TestPollVoteWebhook(t *testing.T) {
	got := make(chan map[string]any, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var p map[string]any
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
			t.Errorf("decode webhook body: %v", err)
		}
		got <- p
	}))
	defer srv.Close()
	t.Setenv("WHATSAPP_WEBHOOK_URL", srv.URL)

	sendPollVoteWebhook("27820000000@s.whatsapp.net", "Dina", "V1", "27820000000", false, PollVote{PollID: "P1", Selected: []string{"ab", "cd"}}, time.Now(), waLog.Noop)
	select {
	case p := <-got:
		msg := p["message"].(map[string]any)
		vote, _ := json.Marshal(msg["poll_vote"])
		if msg["id"] != "V1" || msg["content"] != "" || string(vote) != `{"poll_id":"P1","selected":["ab","cd"]}` {
			t.Fatalf("message = %v", msg)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("no webhook request")
	}
}

func TestWebhookWithoutVoteHasNoPollVote(t *testing.T) {
	b, _ := json.Marshal(WebhookPayload{})
	if strings.Contains(string(b), "poll_vote") {
		t.Fatalf("payload = %s", b)
	}
}

func TestValidatePoll(t *testing.T) {
	ok := SendPollRequest{Recipient: "27820000000", Name: "Klaar?", Options: []string{"1. A", "2. B"}}
	if msg := validatePoll(ok); msg != "" {
		t.Fatalf("valid poll refused: %s", msg)
	}
	bad := []SendPollRequest{
		{Name: "x", Options: []string{"a", "b"}},
		{Recipient: "1", Options: []string{"a", "b"}},
		{Recipient: "1", Name: "x", Options: []string{"a"}},
		{Recipient: "1", Name: "x", Options: []string{"a", "a"}},
		{Recipient: "1", Name: "x", Options: []string{"a", ""}},
		{Recipient: "1", Name: "x", Options: []string{"a", "b"}, SelectableCount: 3},
	}
	for _, req := range bad {
		if validatePoll(req) == "" {
			t.Errorf("accepted %+v", req)
		}
	}
}
