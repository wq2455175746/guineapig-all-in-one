{{- define "release.name" -}}
{{- if .Release -}}
{{- .Release.Name -}}
{{- else -}}
{{- .Values.release.name | default "unknown" -}}
{{- end -}}
{{- end -}}

{{- define "release.namespace" -}}
{{- if .Release -}}
{{- .Release.Namespace -}}
{{- else -}}
{{- .Values.release.namespace | default "default" -}}
{{- end -}}
{{- end -}}


{{- define "validateVolumeConfig" -}}
{{- $validTypes := list "pvc" "hostPath" "configMap" "emptyDir" "secret" -}}
{{- if not (has .type $validTypes) }}
{{- fail (printf "无效的 volume 类型 '%s'。必须是以下之一: %v" .type $validTypes) }}
{{- end }}
{{- if and (eq .type "pvc") (not .pvc) }}
{{- fail "PVC 类型 volume 必须包含 pvc 配置" }}
{{- end }}
{{- if and (eq .type "hostPath") (not .hostPath) }}
{{- fail "hostPath 类型 volume 必须包含 hostPath 配置" }}
{{- end }}
{{- if not .mountPath }}
{{- fail (printf "volume '%s' 必须指定 mountPath" .name) }}
{{- end }}
{{- end -}}
