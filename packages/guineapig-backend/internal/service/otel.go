package service

import (
	"context"
	"errors"
	"fmt"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"time"
)

func ListOtel(ctx context.Context, req *request.OtelListRequest) (*response.OtelListResponse, error) {
	items, total, err := model.MChatOtel.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.OtelItem, 0, len(items))
	for _, item := range items {
		otelValue := ""
		if item.OtelValue != nil {
			otelValue = *item.OtelValue
		}
		otelLabel := ""
		if item.OtelLabel != nil {
			otelLabel = *item.OtelLabel
		}
		convIDs := ""
		if item.ConversationIDs != nil {
			convIDs = *item.ConversationIDs
		}
		resItems = append(resItems, response.OtelItem{
			Id:             item.Id,
			Name:           item.Name,
			UserId:         item.UserId,
			ConversationIDs: convIDs,
			StatDate:       item.StatDate,
			Type:           item.Type,
			OtelValue:      otelValue,
			OtelLabel:      otelLabel,
			CreatedBy:      item.CreatedBy,
			CreatedAt:      item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:      item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.OtelListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

func DeleteOtel(ctx context.Context, req *request.OtelDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}

	existing, err := model.MChatOtel.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}

	return model.MChatOtel.Delete(ctx, req.Id)
}

// GetChartData 通用图表数据查询：根据 chart 名称获取 ECharts 格式数据
func GetChartData(ctx context.Context, req *request.ChartDataRequest) (*response.ChartDataResponse, error) {
	def, ok := chartQueryDefs[req.Chart]
	if !ok {
		return nil, fmt.Errorf("不支持的图表: %s", req.Chart)
	}

	// 默认近 30 天
	startDate := req.StartDate
	endDate := req.EndDate
	if endDate == "" {
		endDate = time.Now().Format("20060102")
	}
	if startDate == "" {
		startDate = time.Now().AddDate(0, 0, -30).Format("20060102")
	}

	var rows []map[string]any
	var err error
	if req.UserId <= 0 {
		// 所有用户数据
		if def.SQLAll == "" {
			return nil, fmt.Errorf("图表 %s 不支持全量查询", req.Chart)
		}
		rows, err = model.MChatOtel.QueryRows(ctx, def.SQLAll, startDate, endDate)
	} else {
		rows, err = model.MChatOtel.QueryRows(ctx, def.SQL, req.UserId, startDate, endDate)
	}
	if err != nil {
		return nil, err
	}

	resp := &response.ChartDataResponse{
		XAxis:  make([]string, 0, len(rows)),
		Series: make([]response.ChartSeriesItem, len(def.Series)),
	}

	for i, s := range def.Series {
		resp.Series[i] = response.ChartSeriesItem{Name: s.Name, Data: make([]float64, 0, len(rows))}
	}

	for _, row := range rows {
		// xAxis
		if xv, ok := row[def.XField]; ok {
			resp.XAxis = append(resp.XAxis, fmt.Sprintf("%v", xv))
		}

		// series
		for i, s := range def.Series {
			var val float64
			if sv, ok := row[s.Field]; ok {
				switch v := sv.(type) {
				case float64:
					val = v
				case int64:
					val = float64(v)
				case string:
					// try to parse as number
					fmt.Sscanf(v, "%f", &val)
				}
			}
			resp.Series[i].Data = append(resp.Series[i].Data, val)
		}
	}

	return resp, nil
}
