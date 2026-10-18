package utils

import (
	"hash/fnv"
	"os"

	"github.com/bwmarrin/snowflake"
)

// snowflakeNodeMax 是 Snowflake 10 位节点 ID 的上界（含）。
const snowflakeNodeMax = 1023

var node *snowflake.Node

// init 初始化 Snowflake 节点。
// 节点 ID 必须全局唯一：多副本若共用同一 nodeID，会在同一毫秒生成相同 ID。
// 因此从实例标识（优先 K8S_POD_NAME，回退主机名）派生，保证各副本不同。
func init() {
	instanceID := os.Getenv("K8S_POD_NAME")
	if instanceID == "" {
		if host, err := os.Hostname(); err == nil {
			instanceID = host
		}
	}
	var err error
	node, err = snowflake.NewNode(hashNodeID(instanceID))
	if err != nil {
		panic(err)
	}
}

// hashNodeID 将实例标识哈希到 Snowflake 的节点 ID 范围 [0, 1023]。
func hashNodeID(instanceID string) int64 {
	h := fnv.New32a()
	_, _ = h.Write([]byte(instanceID))
	return int64(h.Sum32()) % (snowflakeNodeMax + 1)
}

func SnowflakeID() int64 {
	return node.Generate().Int64()
}
