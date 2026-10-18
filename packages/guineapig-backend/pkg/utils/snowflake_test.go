package utils

import "testing"

func TestHashNodeIDInRange(t *testing.T) {
	cases := []string{
		"guineapig-backend-7d9f8b6c4-abcde",
		"guineapig-backend-7d9f8b6c4-fghij",
		"guineapig-backend-7d9f8b6c4-klmno",
		"host-1",
		"",
	}
	for _, c := range cases {
		id := hashNodeID(c)
		if id < 0 || id > snowflakeNodeMax {
			t.Fatalf("hashNodeID(%q) = %d, out of range [0, %d]", c, id, snowflakeNodeMax)
		}
	}
}

func TestHashNodeIDDistinct(t *testing.T) {
	a := hashNodeID("guineapig-backend-7d9f8b6c4-abcde")
	b := hashNodeID("guineapig-backend-7d9f8b6c4-fghij")
	if a == b {
		t.Fatalf("different instances hashed to same node id: %d", a)
	}
}

func TestSnowflakeIDPositive(t *testing.T) {
	if id := SnowflakeID(); id <= 0 {
		t.Fatalf("SnowflakeID() = %d, want > 0", id)
	}
}
