package service

import (
	"context"
	"testing"

	"guineapig/internal/request"
)

func TestEmbedFileValidatesInput(t *testing.T) {
	// Test that EmbedFile validates empty file_id
	_, err := EmbedFile(context.Background(), &request.FileEmbedRequest{
		FileId:    0,
		ResRagId: 1,
	}, 0)
	if err == nil {
		t.Error("expected error for empty file_id, got nil")
	}

	// Test that EmbedFile validates empty res_rag_id
	_, err = EmbedFile(context.Background(), &request.FileEmbedRequest{
		FileId:    1,
		ResRagId: 0,
	}, 0)
	if err == nil {
		t.Error("expected error for empty res_rag_id, got nil")
	}
}

func TestUpdateEmbedProgressValidatesInput(t *testing.T) {
	// Test that UpdateEmbedProgress validates empty file_id
	err := UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId:   0,
		TaskId:   "test",
		Progress: 50,
	})
	if err == nil {
		t.Error("expected error for empty file_id, got nil")
	}

	// Test that UpdateEmbedProgress validates empty task_id
	err = UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId:   1,
		TaskId:   "",
		Progress: 50,
	})
	if err == nil {
		t.Error("expected error for empty task_id, got nil")
	}

	// Test invalid progress range
	err = UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId:   1,
		TaskId:   "test",
		Progress: 101,
	})
	if err == nil {
		t.Error("expected error for invalid progress, got nil")
	}

	err = UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId:   1,
		TaskId:   "test",
		Progress: -1,
	})
	if err == nil {
		t.Error("expected error for invalid progress, got nil")
	}
}

func TestUpdateEmbedProgressErrorHandling(t *testing.T) {
	// Test that UpdateEmbedProgress rejects empty file_id even with error field
	err := UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId:   0,
		TaskId:   "test",
		Progress: 0,
		Error:    "something went wrong",
	})
	if err == nil {
		t.Error("expected error for empty file_id in error report, got nil")
	}

	// Test that UpdateEmbedProgress rejects empty task_id even with error field
	err = UpdateEmbedProgress(context.Background(), &request.FileEmbedProgressRequest{
		FileId: 1,
		TaskId: "",
		Error:  "error without task_id",
	})
	if err == nil {
		t.Error("expected error for empty task_id in error report, got nil")
	}
}
