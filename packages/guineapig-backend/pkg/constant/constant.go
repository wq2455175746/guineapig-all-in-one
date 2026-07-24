package constant

// 相关阶段
const (
	StepNone            = "none"
	StepAudio           = "audio"
	StepAsr             = "asr"
	StepAsrOptimize     = "asrOptimize"
	StepAbstract        = "abstract"
	StepChapterAbstract = "chapterAbstract"
	StepSpeakerAbstract = "speakerAbstract"
	StepMindMap         = "mindMap"
	StepCorrection      = "correction"
)

const (
	AbstractActionChapter = "ChapterAbstract" // 章节纪要-json
	AbstractActionTheme   = "ThemeAbstract"   // 主题纪要-json
	AbstractActionSpeaker = "SpeakerAbstract" // 发言人纪要-json

	AbstractChapter = "chapter"

	LanguageMandarin   = "mandarin"   // 普通话
	LanguageSichuanese = "sichuanese" // 四川话
	LanguageEnglish    = "english"    // 英语
)

// 事件类型
const (
	StatusInit                = "init"
	StatusUploading           = "uploading"
	StatusSoundRecording      = "soundRecording"      // 正在录音
	StatusSoundRecordingPause = "soundRecordingPause" // 录音暂停
	StatusProcessing          = "processing"
	StatusDone                = "done"
	StatusFailed              = "failed"
	StatusCancelled           = "cancelled" // 转译为空
)

// 云会议相关
const (
	CloudMeetingAbsTheme   = "ThemeAbstract"
	CloudMeetingAbsChapter = "ChapterAbstract"
	CloudMeetingAbsSpeaker = "SpeakerAbstract"
)

const (
	EventTypeView        = "view"        // 详情
	EventTypeEdit        = "edit"        // 编辑
	EventTypeEvaluate    = "evaluate"    // 评价
	EventTypeRetry       = "retry"       // 重试
	EventTypeReplace     = "replace"     // 替换
	EventTypeExport      = "export"      // 导出
	EventTypeShareView   = "shareView"   // 分享
	EventTypeComplaint   = "complaint"   // 反馈
	EventTypeDelete      = "delete"      // 删除
	EventTypeUpload      = "upload"      // 上传
	EventTypeListKeyword = "listKeyword" // 列表
	EventTypeCopy        = "copy"        // 复制
)

const (
	SourceFile                 = "file"
	SourceSoundRecording       = "soundRecording"
	SourceExternal             = "external"
	SourceAoneSpace            = "aoneSpace"
	SoundRecordingAlgoMode     = "2pass-offline"            // 二遍校准后的结果
	SoundRecordingFilename     = "soundRecording_%d.pcm"    // 录音文件名
	SoundRecordingOsskey       = "soundRecording_%d.wav"    // 录音oss key
	SoundRecordingStatusPause  = "pause"                    // 暂停状态
	SoundRecordingStatusFinish = "finish"                   // 结束状态
	AdaSoundRecordingFilename  = "adaSoundRecording_%d.pcm" // 录音文件名
	AdaSoundRecordingOsskey    = "adaSoundRecording_%d.wav" // 录音oss key
)

const (
	EvaluateTypeLike    = "like"
	EvaluateTypeDislike = "dislike"
	EvaluateTypeCancel  = "cancel"
)

// 队列相关
const (
	QueueAoneJobFunc = "aone:job:func"     // 注册Aone任务处理方法的名称
	QueueAoneJobTask = "aone:job:task"     // 任务Aone队列名称
	QueueAoneJobId   = "aone:job:%d"       // 用于判断Aone任务是否已经在队列中，setNX的key
	CronAoneInit     = "aone:cron:init"    // 监测不在队列中的Aone定时任务的redis key
	CronAoneProcess  = "aone:cron:process" // 监测处理中心跳的Aone定时任务的redis key
)

const (
	StatusEnable  = 0
	StatusDisable = 1
)

const CYCLE = 86400000 // 毫秒

var EntityTypeMap = map[string]string{
	StepAsr:             StepAsr,
	StepAbstract:        StepAbstract,
	StepChapterAbstract: StepChapterAbstract,
	StepSpeakerAbstract: StepSpeakerAbstract,
}
var InteriorTypeMap = map[string]string{
	"keywords":  "keywords",
	"summary":   "summary",
	"topics":    "topics",
	"summaries": "summaries",
	"qa_pairs":  "qa_pairs",
}
