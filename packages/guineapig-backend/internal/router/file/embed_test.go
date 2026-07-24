package file

import (
	"testing"
	"guineapig/internal/request"
	"guineapig/internal/response"

	"github.com/labstack/echo/v4"
)

// Compile-time assertions: ensure Embed and EmbedProgress are valid handler funcs
var _ echo.HandlerFunc = Embed
var _ echo.HandlerFunc = EmbedProgress

func TestFileEmbedRequest(t *testing.T) {
	req := request.FileEmbedRequest{
		FileId:    123,
		ResRagId: 456,
	}
	if req.FileId != 123 {
		t.Errorf("expected FileId 123, got %d", req.FileId)
	}
	if req.ResRagId != 456 {
		t.Errorf("expected ResRagId 456, got %d", req.ResRagId)
	}
}

func TestFileEmbedProgressRequest(t *testing.T) {
	req := request.FileEmbedProgressRequest{
		FileId:   123,
		TaskId:   "test-task-id",
		Progress: 50,
	}
	if req.FileId != 123 {
		t.Errorf("expected FileId 123, got %d", req.FileId)
	}
	if req.TaskId != "test-task-id" {
		t.Errorf("expected TaskId 'test-task-id', got %s", req.TaskId)
	}
	if req.Progress != 50 {
		t.Errorf("expected Progress 50, got %d", req.Progress)
	}
}

func TestFileEmbedResponse(t *testing.T) {
	resp := response.FileEmbedResponse{
		TaskId: "test-task-id",
	}
	if resp.TaskId != "test-task-id" {
		t.Errorf("expected TaskId 'test-task-id', got %s", resp.TaskId)
	}
}
