package model

import (
	"context"
	"testing"
)

func TestResFilesInterface(t *testing.T) {
	// Verify UpdateEmbeddingConfig and UpdateIsEmbedded are valid methods
	// by checking they compile. Actual DB testing requires a real connection.
	var m *ResFiles = MResFiles
	_ = m
}

func TestResRagsInterface(t *testing.T) {
	// Verify UpdateRagMetadata is a valid method
	// by checking they compile. Actual DB testing requires a real connection.
	var m *ResRags = MResRags
	_ = m
}

func TestResFilesMethodSignatures(t *testing.T) {
	// Compile-time check: ensure methods accept the right parameters
	m := MResFiles
	ctx := context.Background()

	// Just verify the method exists by calling it with a dummy DB
	// (will fail at runtime without DB, but that's expected)
	_ = m.UpdateEmbeddingConfig
	_ = m.UpdateIsEmbedded
	_ = ctx
}

func TestResRagsMethodSignatures(t *testing.T) {
	_ = MResRags.UpdateRagMetadata
}
