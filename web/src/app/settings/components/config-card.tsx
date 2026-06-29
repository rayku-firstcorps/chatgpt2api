"use client";

import { Activity, BellRing, Cloud, LoaderCircle, PlugZap, RefreshCw, Save, Send, ShieldCheck, TimerReset, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ImageStorageMode } from "@/lib/api";
import { testProxy, type ProxyTestResult } from "@/lib/api";

import { useSettingsStore } from "../store";

function formatGuardTime(value?: string | null) {
  if (!value) {
    return "尚未检查";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatDuration(seconds: number) {
  if (!seconds) {
    return "无";
  }
  const minutes = Math.ceil(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟` : `${minutes} 分钟`;
}

const feishuEventLabels = [
  ["triggered", "已自动触发补号"],
  ["skipped_register_config", "注册机配置不完整"],
  ["error", "健康检查异常"],
  ["healthy_recovered", "账号池恢复健康"],
  ["skipped_cooldown", "冷却期跳过"],
  ["skipped_register_running", "注册机运行中跳过"],
] as const;

export function ConfigCard() {
  const [isTestingProxy, setIsTestingProxy] = useState(false);
  const [proxyTestResult, setProxyTestResult] = useState<ProxyTestResult | null>(null);
  const logLevelOptions = ["debug", "info", "warning", "error"];
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setRefreshAccountIntervalMinute = useSettingsStore((state) => state.setRefreshAccountIntervalMinute);
  const setImageRetentionDays = useSettingsStore((state) => state.setImageRetentionDays);
  const setImagePollTimeoutSecs = useSettingsStore((state) => state.setImagePollTimeoutSecs);
  const setImageAccountConcurrency = useSettingsStore((state) => state.setImageAccountConcurrency);
  const setAutoRemoveInvalidAccounts = useSettingsStore((state) => state.setAutoRemoveInvalidAccounts);
  const setAutoRemoveRateLimitedAccounts = useSettingsStore((state) => state.setAutoRemoveRateLimitedAccounts);
  const setLogLevel = useSettingsStore((state) => state.setLogLevel);
  const setProxy = useSettingsStore((state) => state.setProxy);
  const setBaseUrl = useSettingsStore((state) => state.setBaseUrl);
  const setGlobalSystemPrompt = useSettingsStore((state) => state.setGlobalSystemPrompt);
  const setSensitiveWordsText = useSettingsStore((state) => state.setSensitiveWordsText);
  const setAIReviewField = useSettingsStore((state) => state.setAIReviewField);
  const setAccountPoolGuardField = useSettingsStore((state) => state.setAccountPoolGuardField);
  const accountPoolGuard = useSettingsStore((state) => state.accountPoolGuard);
  const feishuAlert = useSettingsStore((state) => state.feishuAlert);
  const setFeishuAlertField = useSettingsStore((state) => state.setFeishuAlertField);
  const setFeishuAlertEvent = useSettingsStore((state) => state.setFeishuAlertEvent);
  const testFeishuAlert = useSettingsStore((state) => state.testFeishuAlert);
  const isTestingFeishuAlert = useSettingsStore((state) => state.isTestingFeishuAlert);
  const setImageStorageField = useSettingsStore((state) => state.setImageStorageField);
  const testImageStorage = useSettingsStore((state) => state.testImageStorage);
  const syncImagesToWebDAV = useSettingsStore((state) => state.syncImagesToWebDAV);
  const isTestingImageStorage = useSettingsStore((state) => state.isTestingImageStorage);
  const isSyncingImageStorage = useSettingsStore((state) => state.isSyncingImageStorage);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const guardState = accountPoolGuard?.state;
  const guardRate = Number(guardState?.last_alive_rate || 0);
  const guardThreshold = Number(config?.account_pool_guard?.alive_rate_threshold || 20);
  const guardIsWarning = Boolean(guardState?.last_checked_at) && guardRate < guardThreshold;
  const guardTone = guardState?.last_action === "triggered"
    ? "border-sky-200 bg-sky-50 text-sky-800"
    : guardIsWarning
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-emerald-200 bg-emerald-50 text-emerald-800";
  const feishuState = feishuAlert?.state;
  const feishuTone = !config?.feishu_alert?.enabled
    ? "border-stone-200 bg-stone-50 text-stone-600"
    : !config.feishu_alert.webhook_configured && !config.feishu_alert.webhook_url
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : feishuState?.last_status === "failed"
        ? "border-rose-200 bg-rose-50 text-rose-800"
        : "border-emerald-200 bg-emerald-50 text-emerald-800";

  const handleTestProxy = async () => {
    const candidate = String(config?.proxy || "").trim();
    if (!candidate) {
      toast.error("请先填写代理地址");
      return;
    }
    setIsTestingProxy(true);
    setProxyTestResult(null);
    try {
      const data = await testProxy(candidate);
      setProxyTestResult(data.result);
      if (data.result.ok) {
        toast.success(`代理可用（${data.result.latency_ms} ms，HTTP ${data.result.status}）`);
      } else {
        toast.error(`代理不可用：${data.result.error ?? "未知错误"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试代理失败");
    } finally {
      setIsTestingProxy(false);
    }
  };

  if (isLoadingConfig) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-4 p-6">
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm leading-6 text-stone-600">
          管理员登录密钥继续从部署配置读取，不再在此页面展示；如需分发给其他人，请在下方创建普通用户密钥。
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">账号刷新间隔</label>
            <Input
              value={String(config?.refresh_account_interval_minute || "")}
              onChange={(event) => setRefreshAccountIntervalMinute(event.target.value)}
              placeholder="分钟"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">单位分钟，控制账号自动刷新频率。</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">全局代理</label>
            <Input
              value={String(config?.proxy || "")}
              onChange={(event) => {
                setProxy(event.target.value);
                setProxyTestResult(null);
              }}
              placeholder="http://127.0.0.1:7890"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">留空表示不使用代理。</p>
            {proxyTestResult ? (
              <div
                className={`rounded-xl border px-3 py-2 text-xs leading-6 ${
                  proxyTestResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {proxyTestResult.ok
                  ? `代理可用：HTTP ${proxyTestResult.status}，用时 ${proxyTestResult.latency_ms} ms`
                  : `代理不可用：${proxyTestResult.error ?? "未知错误"}（用时 ${proxyTestResult.latency_ms} ms）`}
              </div>
            ) : null}
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void handleTestProxy()}
                disabled={isTestingProxy}
              >
                {isTestingProxy ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                测试代理
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">图片访问地址</label>
            <Input
              value={String(config?.base_url || "")}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://example.com"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">用于生成图片结果的访问前缀地址。</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">图片自动清理</label>
            <Input
              value={String(config?.image_retention_days || "")}
              onChange={(event) => setImageRetentionDays(event.target.value)}
              placeholder="30"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">自动删除多少天前的本地图片。</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">图片轮询超时</label>
            <Input
              value={String(config?.image_poll_timeout_secs || "")}
              onChange={(event) => setImagePollTimeoutSecs(event.target.value)}
              placeholder="120"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">单位秒，等待上游图片结果的最长时间。</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">单账号图片并发</label>
            <Input
              value={String(config?.image_account_concurrency || "")}
              onChange={(event) => setImageAccountConcurrency(event.target.value)}
              placeholder="1"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">限制每个账号同时处理的图片请求数量，默认 3。</p>
          </div>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(config?.auto_remove_invalid_accounts)}
              onCheckedChange={(checked) => setAutoRemoveInvalidAccounts(Boolean(checked))}
            />
            自动移除异常账号
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(config?.auto_remove_rate_limited_accounts)}
              onCheckedChange={(checked) => setAutoRemoveRateLimitedAccounts(Boolean(checked))}
            />
            自动移除限流账号
          </label>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-1">
                <label className="flex items-center gap-2 text-sm font-medium text-stone-800">
                  <ShieldCheck className="size-4 text-stone-500" />
                  账号池健康守护
                </label>
                <p className="text-xs leading-6 text-stone-500">
                  系统会按配置周期检查账号池可用账号占比；低于阈值且注册机未运行时，将自动启动注册流程。
                </p>
              </div>
              <label className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.account_pool_guard?.enabled)}
                  onCheckedChange={(checked) => setAccountPoolGuardField("enabled", Boolean(checked))}
                />
                启用
              </label>
            </div>
            <div className={`rounded-lg border px-3 py-3 text-xs leading-6 ${guardTone}`}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="font-medium">{guardState?.last_message || "等待首次健康检查"}</span>
                <span className="inline-flex items-center gap-1">
                  <TimerReset className="size-3.5" />
                  冷却剩余：{formatDuration(Number(accountPoolGuard?.cooldown_remaining_seconds || 0))}
                </span>
              </div>
              <div className="mt-2 grid gap-2 text-stone-600 sm:grid-cols-2 lg:grid-cols-4">
                <span>最近检查：{formatGuardTime(guardState?.last_checked_at)}</span>
                <span>账号总数：{guardState?.last_total_accounts ?? 0}</span>
                <span>存活账号：{guardState?.last_alive_accounts ?? 0}</span>
                <span>存活率：{guardRate.toFixed(1)}% / 阈值 {guardThreshold}%</span>
                <span>最近触发：{formatGuardTime(guardState?.last_triggered_at)}</span>
                <span className="inline-flex items-center gap-1">
                  <Activity className="size-3.5" />
                  注册机：{accountPoolGuard?.register_running ? "运行中" : "空闲"}
                </span>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">检查间隔</label>
                <Input
                  type="number"
                  min={1}
                  value={String(config?.account_pool_guard?.check_interval_minutes || "")}
                  onChange={(event) => setAccountPoolGuardField("check_interval_minutes", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">单位分钟。</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">存活率阈值</label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={String(config?.account_pool_guard?.alive_rate_threshold || "")}
                  onChange={(event) => setAccountPoolGuardField("alive_rate_threshold", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">低于该百分比触发。</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">最小样本数</label>
                <Input
                  type="number"
                  min={0}
                  value={String(config?.account_pool_guard?.min_total_accounts ?? "")}
                  onChange={(event) => setAccountPoolGuardField("min_total_accounts", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">账号数低于此值不触发。</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">触发冷却</label>
                <Input
                  type="number"
                  min={0}
                  value={String(config?.account_pool_guard?.trigger_cooldown_minutes ?? "")}
                  onChange={(event) => setAccountPoolGuardField("trigger_cooldown_minutes", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">单位分钟。</p>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.account_pool_guard?.allow_empty_pool_trigger)}
                  onCheckedChange={(checked) => setAccountPoolGuardField("allow_empty_pool_trigger", Boolean(checked))}
                />
                允许空池触发
              </label>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">触发后的注册目标</label>
                <Select
                  value={String(config?.account_pool_guard?.register_mode || "available")}
                  onValueChange={(value) => setAccountPoolGuardField("register_mode", value)}
                >
                  <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="available">补充正常账号</SelectItem>
                    <SelectItem value="quota">补充剩余额度</SelectItem>
                    <SelectItem value="total">沿用注册机总数</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {config?.account_pool_guard?.register_mode === "quota" ? (
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">目标剩余额度</label>
                  <Input
                    type="number"
                    min={1}
                    value={String(config?.account_pool_guard?.register_target_quota || "")}
                    onChange={(event) => setAccountPoolGuardField("register_target_quota", event.target.value)}
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
              ) : config?.account_pool_guard?.register_mode === "total" ? (
                <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-xs leading-6 text-stone-500">
                  自动触发时沿用注册机当前总数配置，不覆盖邮箱、代理、线程数。
                </div>
              ) : (
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">目标正常账号数</label>
                  <Input
                    type="number"
                    min={1}
                    value={String(config?.account_pool_guard?.register_target_available || "")}
                    onChange={(event) => setAccountPoolGuardField("register_target_available", event.target.value)}
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
              )}
            </div>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-1">
                <label className="flex items-center gap-2 text-sm font-medium text-stone-800">
                  <BellRing className="size-4 text-stone-500" />
                  飞书告警
                </label>
                <p className="text-xs leading-6 text-stone-500">
                  将账号池低存活、补号触发、配置异常和恢复状态推送到飞书群，卡片只包含摘要指标。
                </p>
              </div>
              <label className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.feishu_alert?.enabled)}
                  onCheckedChange={(checked) => setFeishuAlertField("enabled", Boolean(checked))}
                />
                启用
              </label>
            </div>
            <div className={`rounded-lg border px-3 py-3 text-xs leading-6 ${feishuTone}`}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="font-medium">
                  {!config?.feishu_alert?.enabled
                    ? "飞书告警未启用"
                    : feishuState?.last_status === "failed"
                      ? `最近发送失败：${feishuState.last_error || feishuState.last_response_message || "未知错误"}`
                      : feishuState?.last_sent_at
                        ? "最近一次飞书告警发送成功"
                        : "等待首次飞书告警"}
                </span>
                <span>最近发送：{formatGuardTime(feishuState?.last_sent_at)}</span>
              </div>
              <div className="mt-2 grid gap-2 text-stone-600 sm:grid-cols-2 lg:grid-cols-4">
                <span>事件：{feishuState?.last_event_type || "无"}</span>
                <span>结果：{feishuState?.last_status || "idle"}</span>
                <span>返回码：{feishuState?.last_response_code ?? 0}</span>
                <span>Webhook：{config?.feishu_alert?.webhook_configured ? "已配置" : "未配置"}</span>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm text-stone-700">Webhook 地址</label>
                <Input
                  type="password"
                  value={String(config?.feishu_alert?.webhook_url || "")}
                  onChange={(event) => setFeishuAlertField("webhook_url", event.target.value)}
                  placeholder={config?.feishu_alert?.webhook_configured ? "已配置，留空表示沿用原值" : "https://open.feishu.cn/open-apis/bot/v2/hook/..."}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">保存后会脱敏展示，不会在前端返回完整地址。</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">安全关键词</label>
                <Input
                  value={String(config?.feishu_alert?.keyword || "")}
                  onChange={(event) => setFeishuAlertField("keyword", event.target.value)}
                  placeholder="账号池告警"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm text-stone-700">签名密钥</label>
                <Input
                  type="password"
                  value={String(config?.feishu_alert?.secret || "")}
                  onChange={(event) => setFeishuAlertField("secret", event.target.value)}
                  placeholder={config?.feishu_alert?.secret_configured ? "已配置，留空表示沿用原值" : "飞书机器人签名密钥，可留空"}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
              </div>
              <div className="flex items-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                  onClick={() => {
                    setFeishuAlertField("secret", "");
                    setFeishuAlertField("clear_secret", true);
                  }}
                  disabled={!config?.feishu_alert?.secret_configured}
                >
                  <Trash2 className="size-4" />
                  清空密钥
                </Button>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">告警冷却</label>
                <Input
                  type="number"
                  min={0}
                  value={String(config?.feishu_alert?.alert_cooldown_minutes ?? "")}
                  onChange={(event) => setFeishuAlertField("alert_cooldown_minutes", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">同类事件冷却，单位分钟。</p>
              </div>
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.feishu_alert?.recovery_notify)}
                  onCheckedChange={(checked) => setFeishuAlertField("recovery_notify", Boolean(checked))}
                />
                恢复健康通知
              </label>
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.feishu_alert?.include_register_status)}
                  onCheckedChange={(checked) => setFeishuAlertField("include_register_status", Boolean(checked))}
                />
                包含注册机状态
              </label>
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.feishu_alert?.include_manage_link)}
                  onCheckedChange={(checked) => setFeishuAlertField("include_manage_link", Boolean(checked))}
                />
                包含管理入口
              </label>
            </div>
            <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
              <label className="text-sm text-stone-700">告警事件</label>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {feishuEventLabels.map(([event, label]) => (
                  <label key={event} className="flex items-center gap-2 text-sm text-stone-700">
                    <Checkbox
                      checked={Boolean(config?.feishu_alert?.notify_events?.includes(event))}
                      onCheckedChange={(checked) => setFeishuAlertEvent(event, Boolean(checked))}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void testFeishuAlert()}
                disabled={isTestingFeishuAlert}
              >
                {isTestingFeishuAlert ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
                测试发送
              </Button>
            </div>
          </div>
          <div className="space-y-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
            <div>
              <label className="text-sm text-stone-700">控制台日志级别</label>
              <p className="mt-1 text-xs text-stone-500">不选择时使用默认 info / warning / error。</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {logLevelOptions.map((level) => (
                <label key={level} className="flex items-center gap-2 text-sm capitalize text-stone-700">
                  <Checkbox
                    checked={Boolean(config?.log_levels?.includes(level))}
                    onCheckedChange={(checked) => setLogLevel(level, Boolean(checked))}
                  />
                  {level}
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">全局附加指令</label>
            <Textarea
              value={String(config?.global_system_prompt || "")}
              onChange={(event) => setGlobalSystemPrompt(event.target.value)}
              placeholder="例如：先判断用户提示词是否合规；遇到违法、色情、暴力、仇恨等请求时拒绝回答。"
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">每次请求都会作为 system 消息注入，可用于审核用户提示词、避免违规内容、统一约束模型行为或固定角色设定。</p>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">敏感词</label>
            <Textarea
              value={(config?.sensitive_words || []).join("\n")}
              onChange={(event) => setSensitiveWordsText(event.target.value)}
              placeholder="一行一个，命中即拒绝"
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">只要用户请求包含任意敏感词，就直接返回拒绝。</p>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex items-center gap-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.image_storage?.enabled)}
                  onCheckedChange={(checked) => setImageStorageField("enabled", Boolean(checked))}
                />
                启用 WebDAV 图片存储
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                  onClick={() => void testImageStorage()}
                  disabled={isTestingImageStorage || !config?.image_storage?.enabled}
                >
                  {isTestingImageStorage ? <LoaderCircle className="size-4 animate-spin" /> : <Cloud className="size-4" />}
                  测试 WebDAV
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                  onClick={() => void syncImagesToWebDAV()}
                  disabled={isSyncingImageStorage || !config?.image_storage?.enabled || config?.image_storage?.mode === "local"}
                >
                  {isSyncingImageStorage ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                  全量同步
                </Button>
              </div>
            </div>
            <p className="text-xs leading-6 text-stone-500">
              生成时只处理本次新图片；全量同步用于把已有本地图片补传到 WebDAV。
            </p>
            <div className="rounded-lg border border-stone-100 bg-stone-50 px-3 py-2 text-xs text-stone-600">
              当前待保存模式：
              <span className="ml-1 font-medium text-stone-900">
                {config?.image_storage?.enabled
                  ? config.image_storage.mode === "both"
                    ? "本机 + WebDAV"
                    : config.image_storage.mode === "webdav"
                      ? "仅 WebDAV"
                      : "仅本机"
                  : "仅本机"}
              </span>
              <span className="ml-2 text-stone-400">修改后需要点保存，或通过测试/同步按钮自动保存。</span>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">保存模式</label>
                <Select
                  value={String(config?.image_storage?.mode || "local")}
                  onValueChange={(value) => setImageStorageField("mode", value as ImageStorageMode)}
                  disabled={!config?.image_storage?.enabled}
                >
                  <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="local">仅本机</SelectItem>
                    <SelectItem value="webdav">仅 WebDAV</SelectItem>
                    <SelectItem value="both">本机 + WebDAV</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm text-stone-700">WebDAV URL</label>
                <Input
                  value={String(config?.image_storage?.webdav_url || "")}
                  onChange={(event) => setImageStorageField("webdav_url", event.target.value)}
                  placeholder="https://example.com/dav"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">用户名</label>
                <Input
                  value={String(config?.image_storage?.webdav_username || "")}
                  onChange={(event) => setImageStorageField("webdav_username", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">密码</label>
                <Input
                  type="password"
                  value={String(config?.image_storage?.webdav_password || "")}
                  onChange={(event) => setImageStorageField("webdav_password", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">远端目录</label>
                <Input
                  value={String(config?.image_storage?.webdav_root_path || "")}
                  onChange={(event) => setImageStorageField("webdav_root_path", event.target.value)}
                  placeholder="chatgpt2api/images"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2 md:col-span-3">
                <label className="text-sm text-stone-700">公开访问前缀</label>
                <Input
                  value={String(config?.image_storage?.public_base_url || "")}
                  onChange={(event) => setImageStorageField("public_base_url", event.target.value)}
                  placeholder="https://cdn.example.com/chatgpt2api/images"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
                <p className="text-xs text-stone-500">留空时返回本应用 /images/... 代理地址；填入后直接返回公开图片地址。</p>
              </div>
            </div>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <label className="flex items-center gap-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(config?.ai_review?.enabled)}
                onCheckedChange={(checked) => setAIReviewField("enabled", Boolean(checked))}
              />
              启用 AI 审核
            </label>
            <p className="text-xs leading-6 text-stone-500">
              开启后会在请求进入生图账号前先调用审核模型，审核不通过会直接拒绝，减少违规提示词触达账号造成风控或封号的风险。
            </p>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Base URL</label>
                <Input value={String(config?.ai_review?.base_url || "")} onChange={(event) => setAIReviewField("base_url", event.target.value)} placeholder="https://api.openai.com" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">API Key</label>
                <Input value={String(config?.ai_review?.api_key || "")} onChange={(event) => setAIReviewField("api_key", event.target.value)} placeholder="sk-..." className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Model</label>
                <Input value={String(config?.ai_review?.model || "")} onChange={(event) => setAIReviewField("model", event.target.value)} placeholder="gpt-5.4-mini" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">审核提示词</label>
              <Textarea value={String(config?.ai_review?.prompt || "")} onChange={(event) => setAIReviewField("prompt", event.target.value)} placeholder="判断用户请求是否允许。只回答 ALLOW 或 REJECT。" className="min-h-24 rounded-xl border-stone-200 bg-white text-xs shadow-none" />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
            onClick={() => void saveConfig()}
            disabled={isSavingConfig}
          >
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
