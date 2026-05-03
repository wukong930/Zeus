"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Clock, Sparkles, XCircle } from "lucide-react";
import Link from "next/link";
import { type Alert } from "@/data/mock";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { ConfidenceHalo } from "./ConfidenceHalo";
import { timeAgo } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { submitAlertFeedback, submitHumanDecision } from "@/lib/api";

interface AlertCardProps {
  alert: Alert;
  onClick?: () => void;
  glow?: boolean;
}

const severityBorder = {
  critical: "border-l-data-down",
  high: "border-l-severity-high-fg",
  medium: "border-l-brand-orange",
  low: "border-l-data-up",
};

export function AlertCard({ alert, onClick, glow }: AlertCardProps) {
  const [feedbackState, setFeedbackState] = useState<"idle" | "sent" | "error">("idle");
  const [decisionState, setDecisionState] = useState<"idle" | "sent" | "error" | "loading">(
    "idle"
  );

  async function sendFeedback(
    event: React.MouseEvent<HTMLButtonElement>,
    agree: "agree" | "disagree" | "uncertain"
  ) {
    event.stopPropagation();
    try {
      await submitAlertFeedback(
        alert.id,
        agree,
        agree === "agree" ? "will_trade" : agree === "disagree" ? "will_not_trade" : "partial"
      );
      setFeedbackState("sent");
    } catch {
      setFeedbackState("error");
    }
  }

  async function sendDecision(
    event: React.MouseEvent<HTMLButtonElement>,
    decision: "approve" | "reject"
  ) {
    event.stopPropagation();
    setDecisionState("loading");
    try {
      await submitHumanDecision(alert.id, decision);
      setDecisionState("sent");
    } catch {
      setDecisionState("error");
    }
  }

  return (
    <Card
      variant={glow ? "glow" : "flat"}
      glowColor={alert.severity === "critical" ? "red" : "orange"}
      className={cn(
        "border-l-[4px] cursor-pointer transition-all hover:bg-bg-surface-raised",
        severityBorder[alert.severity]
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={alert.severity}>{alert.severity.toUpperCase()}</Badge>
            <span className="text-xs text-text-muted font-mono">{alert.symbol}</span>
            <span className="text-xs text-text-muted">·</span>
            <span className="text-xs text-text-muted">{alert.evaluator}</span>
            {alert.confidenceTier && (
              <Badge variant={alert.humanActionRequired ? "orange" : "neutral"}>
                {alert.confidenceTier}
              </Badge>
            )}
            {alert.llmInvolved && <Badge variant="emerald">LLM</Badge>}
            <div className="flex-1" />
            <span className="text-caption text-text-muted flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {timeAgo(alert.triggeredAt)}
            </span>
          </div>
          <h3 className="text-h3 text-text-primary mb-1">{alert.title}</h3>
          <p className="text-sm text-text-secondary mb-3 leading-relaxed">{alert.narrative}</p>

          {alert.humanActionRequired && (
            <div className="mb-3 flex flex-wrap items-center gap-2 border border-border-subtle bg-bg-surface-highlight px-3 py-2">
              <span className="text-caption text-brand-orange flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                待人工确认
              </span>
              <DecisionButton
                disabled={decisionState === "loading" || decisionState === "sent"}
                onClick={(event) => sendDecision(event, "approve")}
              >
                <CheckCircle2 className="w-3 h-3" />
                通过
              </DecisionButton>
              <DecisionButton
                disabled={decisionState === "loading" || decisionState === "sent"}
                onClick={(event) => sendDecision(event, "reject")}
              >
                <XCircle className="w-3 h-3" />
                拒绝
              </DecisionButton>
              {decisionState === "sent" && (
                <span className="text-caption text-brand-emerald-bright">已提交</span>
              )}
              {decisionState === "error" && (
                <span className="text-caption text-brand-orange">提交失败</span>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 text-caption">
            {alert.adversarialPassed && (
              <span className="text-brand-emerald-bright flex items-center gap-1">
                ✓ Adversarial 3/3
              </span>
            )}
            {alert.counterEvidence.length > 0 && (
              <span className="text-data-down flex items-center gap-1">
                ✕ {alert.counterEvidence.length} 反证
              </span>
            )}
            <span className="text-text-muted">samples · {alert.sampleSize}</span>
            {alert.evaluator === "news_event" && (
              <Link
                href={`/news?symbol=${encodeURIComponent(alert.symbol)}`}
                onClick={(event) => event.stopPropagation()}
                className="text-brand-emerald-bright hover:text-brand-emerald flex items-center gap-1"
              >
                触发新闻
              </Link>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2 text-caption">
            <span className="text-text-muted">反馈</span>
            <FeedbackButton onClick={(event) => sendFeedback(event, "agree")}>同意</FeedbackButton>
            <FeedbackButton onClick={(event) => sendFeedback(event, "uncertain")}>不确定</FeedbackButton>
            <FeedbackButton onClick={(event) => sendFeedback(event, "disagree")}>不同意</FeedbackButton>
            {feedbackState === "sent" && <span className="text-brand-emerald-bright">已记录</span>}
            {feedbackState === "error" && <span className="text-brand-orange">稍后重试</span>}
          </div>
        </div>

        <div className="flex flex-col items-center gap-2 shrink-0">
          <ConfidenceHalo confidence={alert.confidence} sampleSize={alert.sampleSize} />
          <button className="text-caption text-text-muted hover:text-brand-emerald-bright flex items-center gap-1 transition-colors">
            <Sparkles className="w-3 h-3" />
            ⏪ Time Machine
          </button>
        </div>

        <ChevronRight className="w-4 h-4 text-text-muted self-center" />
      </div>
    </Card>
  );
}

function DecisionButton({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="h-7 px-2 rounded-xs border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-surface-raised disabled:opacity-50 disabled:hover:bg-transparent transition-colors flex items-center gap-1"
    >
      {children}
    </button>
  );
}

function FeedbackButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      onClick={onClick}
      className="h-6 px-2 rounded-xs border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-surface-highlight transition-colors"
    >
      {children}
    </button>
  );
}
