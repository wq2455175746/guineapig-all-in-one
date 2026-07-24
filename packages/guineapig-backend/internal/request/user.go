package request

type SearchUserRequest struct {
	Keywords string `query:"keywords"`
}

type DecryptUserInfoRequest struct {
	UserId int64  `query:"userId"`
	Field  string `query:"field"`
}

type ClientLoginRequest struct {
	ApiKey   string `json:"api_key" form:"api_key"`
	DeviceId string `json:"device_id" form:"device_id"`
}

type RegisterRequest struct {
	Email string `json:"email" form:"email"`
	Code  string `json:"code" form:"code"`
}
