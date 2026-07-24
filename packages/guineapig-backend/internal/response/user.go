package response

type SearchUserResponse struct {
	Items []User `json:"items"`
}

type User struct {
	Id       int64  `json:"id,string"`
	UserName string `json:"username"`
	Name     string `json:"name"`
	Email    string `json:"email"`
}

type ListUserResponse struct {
	Users []User `json:"users"`
	Total int64  `json:"total"` // 总用户数
}

type DecryptedUserInfoResponse struct {
	Field string `json:"field"` // 字段名称
	Value string `json:"value"` // 解密后的值
}

type ClientLoginResponse struct {
	UserId int64  `json:"user_id,string"`
	Email  string `json:"email"`
}

type RegisterResponse struct {
	ApiKey string `json:"api_key"`
}
