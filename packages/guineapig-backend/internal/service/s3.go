package service

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"guineapig/config"
	"guineapig/pkg/utils"
	"path/filepath"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4config "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type PresignedUploadResponse struct {
	URL string `json:"url"`
	Key string `json:"key"`
}

type PresignedDownloadResponse struct {
	URL string `json:"url"`
	Key string `json:"key"`
}

func newS3Client(ctx context.Context) (*s3.Client, error) {
	cfg, err := v4config.LoadDefaultConfig(ctx,
		v4config.WithRegion(config.Global.S3.Region),
		v4config.WithCredentialsProvider(
			aws.CredentialsProviderFunc(func(ctx context.Context) (aws.Credentials, error) {
				return aws.Credentials{
					AccessKeyID:     config.Global.S3.AccessKey,
					SecretAccessKey: config.Global.S3.SecretKey,
				}, nil
			}),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("加载 AWS 配置失败: %w", err)
	}

	var s3Opts []func(*s3.Options)
	if config.Global.S3.Endpoint != "" {
		s3Opts = append(s3Opts, func(o *s3.Options) {
			o.BaseEndpoint = aws.String(config.Global.S3.Endpoint)
		})
	}
	if config.Global.S3.ForcePathStyle {
		s3Opts = append(s3Opts, func(o *s3.Options) {
			o.UsePathStyle = true
		})
	}
	return s3.NewFromConfig(cfg, s3Opts...), nil
}

func GeneratePresignedUploadURL(ctx context.Context, userID, filename string) (*PresignedUploadResponse, error) {
	client, err := newS3Client(ctx)
	if err != nil {
		return nil, err
	}
	presignClient := s3.NewPresignClient(client)

	now := time.Now()
	dateStr := now.Format("20060102")
	name := filename
	if name == "" {
		name = utils.UUID()
	}
	key := fmt.Sprintf("audio/asr/%s/%s/%s.mp3", userID, dateStr, name)

	expiry := config.Global.S3.PresignExpiryMinute
	if expiry <= 0 {
		expiry = 15
	}

	presignResult, err := presignClient.PresignPutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(config.Global.S3.Bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(time.Duration(expiry)*time.Minute))
	if err != nil {
		return nil, fmt.Errorf("生成预签名上传 URL 失败: %w", err)
	}

	return &PresignedUploadResponse{
		URL: presignResult.URL,
		Key: key,
	}, nil
}

func GeneratePresignedSkillUploadURL(ctx context.Context, userID, filename string) (*PresignedUploadResponse, error) {
	client, err := newS3Client(ctx)
	if err != nil {
		return nil, err
	}
	presignClient := s3.NewPresignClient(client)

	now := time.Now()
	dateStr := now.Format("20060102")
	name := filename
	if name == "" {
		name = utils.UUID()
	}
	key := fmt.Sprintf("skills/%s/%s/%s.zip", userID, dateStr, name)

	expiry := config.Global.S3.PresignExpiryMinute
	if expiry <= 0 {
		expiry = 15
	}

	presignResult, err := presignClient.PresignPutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(config.Global.S3.Bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(time.Duration(expiry)*time.Minute))
	if err != nil {
		return nil, fmt.Errorf("生成 skill 预签名上传 URL 失败: %w", err)
	}

	return &PresignedUploadResponse{
		URL: presignResult.URL,
		Key: key,
	}, nil
}

func GeneratePresignedResourceUploadURL(ctx context.Context, userID, filename string) (*PresignedUploadResponse, error) {
	client, err := newS3Client(ctx)
	if err != nil {
		return nil, err
	}
	presignClient := s3.NewPresignClient(client)

	now := time.Now()
	dateStr := now.Format("20060102")

	// 用原始文件名的 MD5（不含后缀）替换文件名，保留后缀
	name := filename
	if name != "" {
		ext := filepath.Ext(filename)
		baseName := filename[:len(filename)-len(ext)]
		hash := md5.Sum([]byte(baseName))
		name = hex.EncodeToString(hash[:]) + ext
	} else {
		name = utils.UUID()
	}

	key := fmt.Sprintf("resources/%s/%s/%s", userID, dateStr, name)

	expiry := config.Global.S3.PresignExpiryMinute
	if expiry <= 0 {
		expiry = 15
	}

	presignResult, err := presignClient.PresignPutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(config.Global.S3.Bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(time.Duration(expiry)*time.Minute))
	if err != nil {
		return nil, fmt.Errorf("生成资源文件预签名上传 URL 失败: %w", err)
	}

	return &PresignedUploadResponse{
		URL: presignResult.URL,
		Key: key,
	}, nil
}

func GeneratePresignedDownloadURL(ctx context.Context, key string) (*PresignedDownloadResponse, error) {
	if key == "" {
		return nil, fmt.Errorf("key 不能为空")
	}

	client, err := newS3Client(ctx)
	if err != nil {
		return nil, err
	}
	presignClient := s3.NewPresignClient(client)

	expiry := config.Global.S3.PresignExpiryMinute
	if expiry <= 0 {
		expiry = 15
	}

	presignResult, err := presignClient.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(config.Global.S3.Bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(time.Duration(expiry)*time.Minute))
	if err != nil {
		return nil, fmt.Errorf("生成预签名下载 URL 失败: %w", err)
	}

	return &PresignedDownloadResponse{
		URL: presignResult.URL,
		Key: key,
	}, nil
}
