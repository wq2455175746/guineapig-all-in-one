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

{{/*
可复用的 Pod 模板，供主 Deployment 与 Bot 专用 Deployment 共用。
入参(dict):
  ctx     = 根上下文（$）
  app     = Pod 标签值
  runBots = 是否启动 IM Bot 长连接（true/false）
*/}}
{{- define "guineapig-backend.podTemplate" -}}
template:
  metadata:
    labels:
      app: {{ .app }}
    annotations:
      checksum/config: {{ include (print .ctx.Template.BasePath "/configmap.yaml") .ctx | sha256sum }}
  spec:
    {{- if .ctx.Values.securityContext.enabled }}
    securityContext:
      runAsNonRoot: true
      runAsUser: {{ .ctx.Values.securityContext.runAsUser }}
      runAsGroup: {{ .ctx.Values.securityContext.runAsGroup }}
      fsGroup: {{ .ctx.Values.securityContext.fsGroup }}
    {{- end }}
    {{- if .ctx.Values.rbac.enabled }}
    serviceAccountName: {{ .ctx.Values.deployment.name }}-sa
    {{- end }}
    {{- if .ctx.Values.persistence }}
    volumes:
      {{- range $name, $config := .ctx.Values.persistence }}
      {{- if $config.enabled }}
      - name: {{ $name }}-volume
        {{- if eq $config.type "pvc" }}
        persistentVolumeClaim:
          claimName: {{ $config.existingClaim | default (printf "%s-%s-pvc" $.ctx.Values.deployment.name $name) }}
        {{- else if eq $config.type "hostPath" }}
        hostPath:
          path: {{ $config.hostPath.path }}
          type: {{ $config.hostPath.type | default "Directory" }}
        {{- else if eq $config.type "configMap" }}
        configMap:
          name: {{ $config.configMap.name | default (printf "%s-%s-cm" $.ctx.Values.deployment.name $name) }}
          {{- if $config.configMap.items }}
          items:
          {{- range $key, $val := $config.configMap.items }}
          - key: {{ $val.key }}
            path: {{ $val.path }}
          {{- end }}
          {{- end }}
        {{- else if eq $config.type "secret" }}
        secret:
          secretName: {{ $config.secret.secretName | default (printf "%s-%s-secret" $.ctx.Values.deployment.name $name) }}
          {{- if $config.secret.defaultMode }}
          defaultMode: {{ $config.secret.defaultMode }}
          {{- end }}
          {{- if $config.secret.optional }}
          optional: {{ $config.secret.optional }}
          {{- end }}
          {{- if $config.secret.items }}
          items:
          {{- range $key, $val := $config.secret.items }}
          - key: {{ $val.key }}
            path: {{ $val.path }}
          {{- end }}
          {{- end }}
        {{- else if eq $config.type "emptyDir" }}
        emptyDir:
          {{- if $config.emptyDir }}
          {{- with $config.emptyDir }}
          {{- if .medium }}
          medium: {{ .medium }}
          {{- end }}
          {{- if .sizeLimit }}
          sizeLimit: {{ .sizeLimit }}
          {{- end }}
          {{- end }}
          {{- end }}
        {{- else }}
          {{- fail (printf "不支持的 volume 类型: %s" $config.type) }}
        {{- end }}
      {{- end }}
      {{- end }}
    {{- end }}

    {{- if .ctx.Values.deployment.initContainer.enabled }}
    initContainers:
    - name: {{ .ctx.Values.deployment.initContainer.name }}
      image: {{ .ctx.Values.deployment.initContainer.image  }}
      imagePullPolicy: {{ .ctx.Values.deployment.initContainer.imagePullPolicy}}
      {{- if .ctx.Values.deployment.initContainer.command }}
      command:
        {{- toYaml .ctx.Values.deployment.initContainer.command | nindent 8 }}
      {{- end }}
      {{- if .ctx.Values.deployment.initContainer.args }}
      args: {{ .ctx.Values.deployment.initContainer.args | toJson }}
      {{- end }}
      {{- if .ctx.Values.deployment.initContainer.volumeMounts }}
      volumeMounts:
      {{- range $, $config := .ctx.Values.deployment.initContainer.volumeMounts }}
      - name: {{ $config.name }}-volume
        mountPath: {{ $config.mountPath }}
        {{- if $config.subPath }}
        subPath: {{ $config.subPath }}
        {{- end }}
        {{- if $config.readOnly }}
        readOnly: {{ $config.readOnly }}
        {{- end }}
      {{- end }}
      {{- end }}
      {{- if .ctx.Values.deployment.initContainer.env }}
      env:
        {{- toYaml .ctx.Values.deployment.initContainer.env | nindent 8 }}
      {{- end }}
    {{- end }}
    containers:
    - name: {{ .ctx.Values.deployment.container.name }}
      image: {{ .ctx.Values.deployment.container.image }}
      {{- if .ctx.Values.deployment.container.command }}
      command:
        {{- toYaml .ctx.Values.deployment.container.command | nindent 8 }}
      {{- end }}
      {{- if .ctx.Values.deployment.container.args }}
      args: {{ .ctx.Values.deployment.container.args | toJson }}
      {{- end }}
      ports:
      {{- range $, $config := .ctx.Values.deployment.container.ports }}
      - name: {{ $config.name }}
        containerPort: {{ $config.containerPort }}
        protocol: {{ $config.protocol }}
      {{- end -}}
      {{- if .ctx.Values.deployment.container.envFrom }}
      envFrom:
        {{- with .ctx.Values.deployment.container.envFrom }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      {{- end }}
      env:
        - name: RUN_BOTS
          value: {{ .runBots | quote }}
        {{- with .ctx.Values.deployment.container.env }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      {{- if and .ctx.Values.persistence (not (empty .ctx.Values.persistence)) }}
      volumeMounts:
        {{- range $name, $config := .ctx.Values.persistence }}
        {{- if $config.enabled }}
        {{- if eq $config.type "pvc" }}
        {{- range $key, $val := $config.volumeMounts }}
        - name: {{ $name }}-volume
          mountPath: {{ $val.mountPath }}
          {{- if $val.subPath }}
          subPath: {{ $val.subPath }}
          {{- end }}
        {{- end }}
        {{- else if eq $config.type "configMap" }}
        {{- range $key, $val := $config.configMap.items }}
        - name: {{ $name }}-volume
          mountPath: {{ $val.mountPath }}
          {{- if $val.subPath }}
          subPath: {{ $val.subPath }}
          {{- end }}
          {{- if $val.readOnly }}
          readOnly: {{ $val.readOnly }}
          {{- end }}
        {{- end }}
        {{- else if eq $config.type "secret" }}
        {{- range $key, $val := $config.secret.items }}
        - name: {{ $name }}-volume
          mountPath: {{ $val.mountPath }}
          {{- if $val.subPath }}
          subPath: {{ $val.subPath }}
          {{- end }}
          {{- if $val.readOnly }}
          readOnly: {{ $val.readOnly }}
          {{- end }}
        {{- end }}
        {{- else }}
        - name: {{ $name }}-volume
          mountPath: {{ $config.mountPath }}
          {{- if $config.subPath }}
          subPath: {{ $config.subPath }}
          {{- end }}
          {{- if $config.readOnly }}
          readOnly: {{ $config.readOnly }}
          {{- end }}
        {{- end }}
        {{- end }}
        {{- end }}
      {{- end }}
      resources: {{- toYaml .ctx.Values.deployment.container.resources | nindent 8 }}
      {{- if .ctx.Values.deployment.container.livenessProbe }}
      livenessProbe: {{- toYaml .ctx.Values.deployment.container.livenessProbe | nindent 8 }}
      {{ end }}
      {{- if .ctx.Values.deployment.container.readinessProbe }}
      readinessProbe: {{- toYaml .ctx.Values.deployment.container.readinessProbe | nindent 8 }}
      {{ end }}
      {{- if .ctx.Values.deployment.container.startupProbe }}
      startupProbe: {{- toYaml .ctx.Values.deployment.container.startupProbe | nindent 8 }}
      {{ end }}
      {{- if .ctx.Values.deployment.container.lifecycle }}
      lifecycle: {{- toYaml .ctx.Values.deployment.container.lifecycle | nindent 8 }}
      {{- end }}
      terminationMessagePath: /dev/termination-log
      terminationMessagePolicy: File
      imagePullPolicy: {{ .ctx.Values.deployment.container.imagePullPolicy }}
    restartPolicy: {{ .ctx.Values.deployment.container.restartPolicy }}
    terminationGracePeriodSeconds: {{ .ctx.Values.deployment.container.terminationGracePeriodSeconds }}
    dnsPolicy: {{ .ctx.Values.deployment.container.dnsPolicy }}
    {{- with .ctx.Values.affinity }}
    affinity:
      {{- toYaml . | nindent 6 }}
      {{- end }}
    {{- with .ctx.Values.nodeSelector }}
    nodeSelector:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- with .ctx.Values.tolerations }}
    tolerations:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- if .ctx.Values.deployment.imagePullSecrets}}
    imagePullSecrets:
    {{- with .ctx.Values.deployment.imagePullSecrets }}
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- end }}
    {{- if .ctx.Values.deployment.schedulerName }}
    schedulerName: {{ .ctx.Values.deployment.schedulerName | default "" }}
    {{- end }}
    {{- if .ctx.Values.deployment.hostAliases }}
    hostAliases:
    {{- with .ctx.Values.deployment.hostAliases }}
      {{- toYaml . | nindent 4 }}
    {{- end }}
    {{- end }}
{{- end -}}
