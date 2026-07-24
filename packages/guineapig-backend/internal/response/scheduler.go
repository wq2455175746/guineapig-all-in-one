package response

// SchedulerEntryItem 定时调度任务条目
type SchedulerEntryItem struct {
	ID          string `json:"id"`
	TaskType    string `json:"taskType"`
	Spec        string `json:"spec"`
	NextEnqueue string `json:"nextEnqueue"`
	PrevEnqueue string `json:"prevEnqueue"`
	Description string `json:"description"`
}

// SchedulerListResponse 调度任务列表响应
type SchedulerListResponse struct {
	Entries []SchedulerEntryItem `json:"entries"`
}
