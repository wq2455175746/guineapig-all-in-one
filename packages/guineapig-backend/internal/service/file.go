package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/plugin"
	"guineapig/pkg/utils"

	"github.com/google/uuid"
)

// FileMetadata JSON 结构
type FileMetadata struct {
	Size int64  `json:"size"`
	Md5  string `json:"md5"`
}

// EmbeddingConfigData embedding config JSON 结构
type EmbeddingConfigData struct {
	EmbeddingProcess int    `json:"embedding_process"`
	ResRagId         int64  `json:"res_rag_id"`
	TaskId           string `json:"task_id"`
	Error            string `json:"error,omitempty"`
}

// RagMetadataData rag metadata JSON 结构
type RagMetadataData struct {
	IsUsed bool `json:"is_used"`
}

func CreateFile(ctx context.Context, req *request.FileCreateRequest) (*response.FileCreateResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}
	if req.Name == "" {
		return nil, errors.New("文件名不能为空")
	}
	if req.FileURL == "" {
		return nil, errors.New("file_url 不能为空")
	}

	// 检查同名文件是否已存在
	existing, err := model.MResFiles.FindByUserIdAndName(ctx, req.UserId, req.Name)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("同名文件已存在")
	}

	// 构建 file_metadata JSON
	meta := FileMetadata{
		Size: req.FileSize,
		Md5:  req.FileMd5,
	}
	metaBytes, _ := json.Marshal(meta)

	m := &model.ResFiles{
		UserId:       req.UserId,
		Name:         req.Name,
		FileDesc:     req.FileDesc,
		FileURL:      req.FileURL,
		FileMetadata: string(metaBytes),
		FileType:     req.FileType,
		IsEmbedded:   0,
		StorageType:  req.StorageType,
	}

	if err := m.Create(ctx); err != nil {
		return nil, err
	}

	return &response.FileCreateResponse{Id: m.Id}, nil
}

func UpdateFile(ctx context.Context, req *request.FileUpdateRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResFiles.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	m := &model.ResFiles{
		Id:       req.Id,
		Name:     req.Name,
		FileDesc: req.FileDesc,
		FileType: req.FileType,
	}
	return m.Update(ctx)
}

func DeleteFile(ctx context.Context, req *request.FileDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResFiles.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	// 解析 embedding_config，判断是否需要删除 Milvus 向量
	if existing.EmbeddingConfig != nil && *existing.EmbeddingConfig != "" {
		var embedConfig EmbeddingConfigData
		if err := json.Unmarshal([]byte(*existing.EmbeddingConfig), &embedConfig); err == nil {
			if embedConfig.ResRagId > 0 && (existing.IsEmbedded == 1 || existing.IsEmbedded == 2) {
				// 查找 RAG 知识库名称（即 Milvus 集合名称）
				rag, err := model.MResRags.FindById(ctx, embedConfig.ResRagId)
				if err == nil && rag != nil {
					deleteParams := map[string]any{
						"file_id":  req.Id,
						"rag_name": rag.Name,
					}
					go callAiAgentDeleteEmbeddings(context.Background(), deleteParams)
				}
			}
		}
	}

	return model.MResFiles.Delete(ctx, req.Id, req.UserId)
}

func ListFile(ctx context.Context, req *request.FileListRequest) (*response.FileListResponse, error) {
	items, total, err := model.MResFiles.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.FileItem, 0, len(items))
	for _, item := range items {
		fileSize, fileMd5 := parseFileMetadata(item.FileMetadata)
		resItems = append(resItems, response.FileItem{
			Id:              item.Id,
			UserId:          item.UserId,
			Name:            item.Name,
			FileDesc:        item.FileDesc,
			FileURL:         item.FileURL,
			FileSize:        fileSize,
			FileMd5:         fileMd5,
			FileType:        item.FileType,
			IsEmbedded:      item.IsEmbedded,
			StorageType:     item.StorageType,
			EmbeddingConfig: getEmbeddingConfig(item.EmbeddingConfig),
			CreatedAt:       item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:       item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.FileListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

// getEmbeddingConfig 安全获取 embedding_config 字符串
func getEmbeddingConfig(ec *string) string {
	if ec == nil {
		return ""
	}
	return *ec
}
func parseFileMetadata(metaStr string) (int64, string) {
	if metaStr == "" {
		return 0, ""
	}
	var meta FileMetadata
	if err := json.Unmarshal([]byte(metaStr), &meta); err != nil {
		return 0, ""
	}
	return meta.Size, meta.Md5
}

// PresignedUploadURL 生成资源文件上传预签名 URL
func PresignedResourceUploadURL(ctx context.Context, userID, filename string) (*PresignedUploadResponse, error) {
	if userID == "" {
		return nil, errors.New("user_id 不能为空")
	}
	return GeneratePresignedResourceUploadURL(ctx, userID, filename)
}

// PresignedDownloadURLByKey 生成资源文件下载预签名 URL
func PresignedResourceDownloadURL(ctx context.Context, key string) (*PresignedDownloadResponse, error) {
	if key == "" {
		return nil, errors.New("key 不能为空")
	}
	return GeneratePresignedDownloadURL(ctx, key)
}

// GetFileById 查询单条文件记录
func GetFileById(ctx context.Context, id int64) (*response.FileItem, error) {
	m, err := model.MResFiles.FindById(ctx, id)
	if err != nil {
		return nil, err
	}
	if m == nil {
		return nil, nil
	}
	fileSize, fileMd5 := parseFileMetadata(m.FileMetadata)
	return &response.FileItem{
		Id:              m.Id,
		UserId:          m.UserId,
		Name:            m.Name,
		FileDesc:        m.FileDesc,
		FileURL:         m.FileURL,
		FileSize:        fileSize,
		FileMd5:         fileMd5,
		FileType:        m.FileType,
		IsEmbedded:      m.IsEmbedded,
		StorageType:     m.StorageType,
		EmbeddingConfig: getEmbeddingConfig(m.EmbeddingConfig),
		CreatedAt:       m.CreatedAt.Format(time.DateTime),
		UpdatedAt:       m.UpdatedAt.Format(time.DateTime),
	}, nil
}

// EmbedFile 文件嵌入知识库
// EmbedFile 触发文件嵌入任务。requesterUserID 为 Token 推导的 caller identity（0 表示 admin 会话）。
func EmbedFile(ctx context.Context, req *request.FileEmbedRequest, requesterUserID int64) (*response.FileEmbedResponse, error) {
	if req.FileId <= 0 {
		return nil, errors.New("file_id 不能为空")
	}
	if req.ResRagId <= 0 {
		return nil, errors.New("res_rag_id 不能为空")
	}

	// 1. 查找文件
	file, err := model.MResFiles.FindById(ctx, req.FileId)
	if err != nil {
		return nil, err
	}
	if file == nil {
		return nil, errors.New("文件不存在")
	}
	// 文件属主校验，杜绝 IDOR
	if requesterUserID > 0 && file.UserId != requesterUserID {
		return nil, errors.New("无权操作该文件")
	}

	// 2. 查找 RAG 知识库
	rag, err := model.MResRags.FindById(ctx, req.ResRagId)
	if err != nil {
		return nil, err
	}
	if rag == nil {
		return nil, errors.New("知识库不存在")
	}
	if requesterUserID > 0 && rag.UserId != requesterUserID {
		return nil, errors.New("无权操作该知识库")
	}

	// 3. 获取 embedding 模型信息
	embeddingModel, err := model.MUserAiModel.FindById(ctx, rag.EmbeddingModelId)
	if err != nil {
		return nil, fmt.Errorf("查询嵌入模型失败: %w", err)
	}
	if embeddingModel == nil {
		return nil, errors.New("嵌入模型不存在")
	}

	// 4. 生成 task_id
	taskId := uuid.New().String()

	// 5. 更新 file.embedding_config 和 is_embedded = 2 (嵌入中)
	embedConfig := EmbeddingConfigData{
		EmbeddingProcess: 0,
		ResRagId:         req.ResRagId,
		TaskId:           taskId,
	}
	embedBytes, _ := json.Marshal(embedConfig)
	embedStr := string(embedBytes)
	if err := model.MResFiles.UpdateEmbeddingConfig(ctx, req.FileId, embedStr); err != nil {
		return nil, fmt.Errorf("更新 embedding_config 失败: %w", err)
	}
	if err := model.MResFiles.UpdateIsEmbedded(ctx, req.FileId, model.IsEmbeddedDoing); err != nil {
		return nil, fmt.Errorf("更新 is_embedded 状态失败: %w", err)
	}

	// 6. 更新 rag.rag_metadata (is_used = true)
	ragMeta := RagMetadataData{IsUsed: true}
	ragMetaBytes, _ := json.Marshal(ragMeta)
	ragMetaStr := string(ragMetaBytes)
	if err := model.MResRags.UpdateRagMetadata(ctx, req.ResRagId, ragMetaStr); err != nil {
		return nil, fmt.Errorf("更新 rag_metadata 失败: %w", err)
	}

	// 7. 获取文件的完整 S3 URL
	s3Key := file.FileURL

	// 8. 异步调用 aiagent
	aiParams := map[string]any{
		"file_id":              req.FileId,
		"res_rag_id":           req.ResRagId,
		"task_id":              taskId,
		"rag_name":             rag.Name,
		"chunk_size":           rag.ChunkSize,
		"overlap_size":         rag.OverlapSize,
		"dimension_size":       rag.DimensionSize,
		"embedding_model_url":  embeddingModel.ApiUrl,
		"embedding_model_name": embeddingModel.ModelName,
		"s3_key":               s3Key,
		"user_id":              file.UserId,
	}

	go callAiAgentEmbedFile(context.Background(), aiParams)

	return &response.FileEmbedResponse{TaskId: taskId}, nil
}

type aiagentEmbedResponse struct {
	Success    bool   `json:"success"`
	ErrCode    int    `json:"errCode"`
	ErrMessage string `json:"errMessage"`
	Result     any    `json:"result"`
}

func callAiAgentEmbedFile(ctx context.Context, params map[string]any) {
	// 后台任务 context：整体 30s 超时，避免 goroutine 悬挂（含错误回写 DB）
	ctx, cancel := context.WithTimeout(ctx, utils.HTTPRequestTimeout)
	defer cancel()

	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		errMsg := "AIAGENT_BASE_URL 未配置，跳过 aiagent 调用"
		log.Printf("[EmbedFile] %s", errMsg)
		reportAiAgentError(ctx, params, errMsg)
		return
	}

	reqBody, err := json.Marshal(params)
	if err != nil {
		errMsg := fmt.Sprintf("序列化请求参数失败: %v", err)
		log.Printf("[EmbedFile] %s", errMsg)
		reportAiAgentError(ctx, params, errMsg)
		return
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/rag/embed",
		bytes.NewReader(reqBody))
	if err != nil {
		errMsg := fmt.Sprintf("创建 HTTP 请求失败: %v", err)
		log.Printf("[EmbedFile] %s", errMsg)
		reportAiAgentError(ctx, params, errMsg)
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := utils.NewHTTPClient(30 * time.Second)
	resp, err := client.Do(httpReq)
	if err != nil {
		errMsg := fmt.Sprintf("调用 aiagent 失败: %v", err)
		log.Printf("[EmbedFile] %s", errMsg)
		reportAiAgentError(ctx, params, errMsg)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		errMsg := fmt.Sprintf("aiagent 返回非 200 状态码: %d", resp.StatusCode)
		log.Printf("[EmbedFile] %s, file_id=%v", errMsg, params["file_id"])
		reportAiAgentError(ctx, params, errMsg)
		return
	}
	log.Printf("[EmbedFile] 成功调用 aiagent: file_id=%v", params["file_id"])
}

func callAiAgentDeleteEmbeddings(ctx context.Context, params map[string]any) {
	// 后台任务 context：整体 30s 超时，避免 goroutine 悬挂
	ctx, cancel := context.WithTimeout(ctx, utils.HTTPRequestTimeout)
	defer cancel()

	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		log.Printf("[DeleteEmbeddings] AIAGENT_BASE_URL 未配置，跳过 Milvus 清理")
		return
	}

	reqBody, err := json.Marshal(params)
	if err != nil {
		log.Printf("[DeleteEmbeddings] 序列化请求参数失败: %v", err)
		return
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/rag/delete-embeddings",
		bytes.NewReader(reqBody))
	if err != nil {
		log.Printf("[DeleteEmbeddings] 创建 HTTP 请求失败: %v", err)
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := utils.NewHTTPClient(30 * time.Second)
	resp, err := client.Do(httpReq)
	if err != nil {
		log.Printf("[DeleteEmbeddings] 调用 aiagent 删除嵌入失败: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Printf("[DeleteEmbeddings] aiagent 返回非 200 状态码: %d, file_id=%v", resp.StatusCode, params["file_id"])
		return
	}
	log.Printf("[DeleteEmbeddings] 成功删除 Milvus 嵌入: file_id=%v", params["file_id"])
}

// reportAiAgentError 当 aiagent 调用失败时，更新 is_embedded=9 并记录错误信息
func reportAiAgentError(ctx context.Context, params map[string]any, errMsg string) {
	fileID, ok := params["file_id"].(int64)
	if !ok {
		log.Printf("[EmbedFile] 无法获取 file_id 参数（类型断言失败）")
		return
	}
	taskID, _ := params["task_id"].(string)

	// 更新 is_embedded = 9 (嵌入失败)
	if err := model.MResFiles.UpdateIsEmbedded(ctx, fileID, model.IsEmbeddedFailed); err != nil {
		log.Printf("[EmbedFile] 更新 is_embedded 失败状态出错: %v", err)
	}

	// 更新 embedding_config 记录错误信息
	if err := updateFileEmbedError(ctx, fileID, errMsg); err != nil {
		log.Printf("[EmbedFile] 更新 embedding_config 错误信息出错: %v", err)
	}

	log.Printf("[EmbedFile] 已记录 aiagent 调用失败: file_id=%d, task_id=%s, error=%s", fileID, taskID, errMsg)
}

// updateFileEmbeddingProgress 更新文件 embedding_config 中的进度值（公共 helper）
func updateFileEmbeddingProgress(ctx context.Context, fileId int64, progress int) error {
	file, err := model.MResFiles.FindById(ctx, fileId)
	if err != nil {
		return fmt.Errorf("查找文件失败: %w", err)
	}
	if file == nil {
		return errors.New("文件不存在")
	}

	var embedConfig EmbeddingConfigData
	if file.EmbeddingConfig != nil {
		if err := json.Unmarshal([]byte(*file.EmbeddingConfig), &embedConfig); err != nil {
			return fmt.Errorf("解析 embedding_config 失败: %w", err)
		}
	}
	embedConfig.EmbeddingProcess = progress
	embedBytes, err := json.Marshal(embedConfig)
	if err != nil {
		return fmt.Errorf("序列化 embedding_config 失败: %w", err)
	}
	return model.MResFiles.UpdateEmbeddingConfig(ctx, fileId, string(embedBytes))
}

// updateFileEmbedError 更新文件 embedding_config 中的错误信息
func updateFileEmbedError(ctx context.Context, fileId int64, errMsg string) error {
	file, err := model.MResFiles.FindById(ctx, fileId)
	if err != nil {
		return fmt.Errorf("查找文件失败: %w", err)
	}
	if file == nil {
		return errors.New("文件不存在")
	}

	var embedConfig EmbeddingConfigData
	if file.EmbeddingConfig != nil {
		if err := json.Unmarshal([]byte(*file.EmbeddingConfig), &embedConfig); err != nil {
			return fmt.Errorf("解析 embedding_config 失败: %w", err)
		}
	}
	embedConfig.Error = errMsg
	embedBytes, err := json.Marshal(embedConfig)
	if err != nil {
		return fmt.Errorf("序列化 embedding_config 失败: %w", err)
	}
	return model.MResFiles.UpdateEmbeddingConfig(ctx, fileId, string(embedBytes))
}

// UpdateEmbedProgress 更新文件嵌入进度
func UpdateEmbedProgress(ctx context.Context, req *request.FileEmbedProgressRequest) error {
	if req.FileId <= 0 {
		return errors.New("file_id 不能为空")
	}
	if req.TaskId == "" {
		return errors.New("task_id 不能为空")
	}

	// 处理错误上报：当 error 不为空时，标记嵌入失败
	if req.Error != "" {
		// 1. 设置 file.is_embedded = 9 (嵌入失败)
		if err := model.MResFiles.UpdateIsEmbedded(ctx, req.FileId, model.IsEmbeddedFailed); err != nil {
			return fmt.Errorf("更新 is_embedded 失败状态失败: %w", err)
		}

		// 2. 更新 embedding_config 记录错误信息
		if err := updateFileEmbedError(ctx, req.FileId, req.Error); err != nil {
			return err
		}

		// 3. 删除 Redis key（如果存在）
		redisKey := fmt.Sprintf("rag_embedding_task:%d:%s", req.FileId, req.TaskId)
		plugin.GetClient().Del(ctx, redisKey)

		return nil
	}

	if req.Progress < 0 || req.Progress > 100 {
		return errors.New("progress 必须介于 0-100")
	}

	redisKey := fmt.Sprintf("rag_embedding_task:%d:%s", req.FileId, req.TaskId)

	if req.Progress == 100 {
		// 1. 设置 file.is_embedded = 1 (已嵌入)
		if err := model.MResFiles.UpdateIsEmbedded(ctx, req.FileId, model.IsEmbeddedYes); err != nil {
			return fmt.Errorf("更新 is_embedded 失败: %w", err)
		}

		// 2. 更新 embedding_config 中 progress = 100
		if err := updateFileEmbeddingProgress(ctx, req.FileId, 100); err != nil {
			return err
		}

		// 3. 删除 Redis key
		plugin.GetClient().Del(ctx, redisKey)
	} else {
		// 更新进度到 Redis
		plugin.GetClient().Set(ctx, redisKey, req.Progress, 24*time.Hour)

		// 同步更新 DB embedding_config
		if err := updateFileEmbeddingProgress(ctx, req.FileId, req.Progress); err != nil {
			return err
		}
	}

	return nil
}
