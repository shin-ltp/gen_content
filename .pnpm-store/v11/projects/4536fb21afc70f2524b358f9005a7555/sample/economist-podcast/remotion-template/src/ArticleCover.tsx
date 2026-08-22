import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { VideoMetadata } from "./types";
import { ARTICLE_COLORS } from "./constants";
import { Timeline } from "./Timeline";

const CHANNEL_LOGO_PATH = staticFile("channel_logo.png");
const OVERLAY_LOGO_PATH = staticFile("logo_red.svg");

interface ArticleCoverProps {
  metadata: VideoMetadata;
  articleIndex: number;
}

export const ArticleCover: React.FC<ArticleCoverProps> = ({
  metadata,
  articleIndex,
}) => {
  const { articles, issueDate } = metadata;
  const article = articles[articleIndex];
  if (!article) return null;

  const color = ARTICLE_COLORS[articleIndex % ARTICLE_COLORS.length];
  const imageSrc = article.imagePath ? staticFile(article.imagePath) : null;

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#fff",
      }}
    >
      {/* Main content: left-right split */}
      <div style={{ display: "flex", flexDirection: "row", flex: 1, minHeight: 0 }}>
        {/* Left Panel */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: "58%",
            height: "100%",
            padding: "40px 50px 24px",
            backgroundColor: "#f9fafb",
            borderRight: "1px solid #e5e7eb",
          }}
        >
          {/* Channel Logo + Name */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              flexShrink: 0,
            }}
          >
            <div style={{ width: 110, height: 110, flexShrink: 0 }}>
              <Img
                src={CHANNEL_LOGO_PATH}
                style={{ width: "100%", height: "100%", objectFit: "contain" }}
              />
            </div>
            <span
              style={{
                fontSize: 44,
                fontWeight: 900,
                color: "#162557",
                letterSpacing: 2,
              }}
            >
              GLOBAL CLIP
            </span>
          </div>

          {/* Article Content — wrapper for vertical centering */}
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              marginTop: 16,
            }}
          >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 20,
              borderLeft: `8px solid ${color}`,
              paddingLeft: 28,
            }}
          >
            {/* Section Badge */}
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div
                style={{
                  fontSize: 30,
                  fontWeight: 700,
                  color: "#fff",
                  backgroundColor: color,
                  borderRadius: 6,
                  padding: "4px 18px",
                  letterSpacing: 1,
                }}
              >
                {article.sectionLabel}
              </div>
              <span
                style={{ fontSize: 28, fontWeight: 600, color: "#6b7280" }}
              >
                {issueDate}
              </span>
            </div>

            {/* English Title */}
            <div
              style={{
                fontSize: 32,
                fontWeight: 600,
                color: "#6b7280",
                lineHeight: 1.3,
                fontStyle: "italic",
              }}
            >
              {article.originalTitle}
            </div>

            {/* Japanese Title */}
            <div
              style={{
                fontSize: 52,
                fontWeight: 900,
                color: "#111827",
                lineHeight: 1.25,
              }}
            >
              {article.japaneseTitle}
            </div>

            {/* Summary */}
            <div
              style={{
                fontSize: 32,
                fontWeight: 500,
                color: "#374151",
                lineHeight: 1.55,
                marginTop: 4,
              }}
            >
              {article.summaryJa}
            </div>
          </div>
          </div>
        </div>

        {/* Right Panel */}
        <div
          style={{
            position: "relative",
            width: "42%",
            height: "100%",
            backgroundColor: "#f9fafb",
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {imageSrc ? (
            <Img
              src={imageSrc}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
              }}
            />
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                color: "#9ca3af",
                fontSize: 24,
              }}
            >
              No Image
            </div>
          )}

          {/* Overlay Logo */}
          <div
            style={{
              position: "absolute",
              top: 40,
              left: 40,
              width: 256,
              filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.4))",
            }}
          >
            <Img
              src={OVERLAY_LOGO_PATH}
              style={{ width: "100%", height: "auto" }}
            />
          </div>
        </div>
      </div>

      {/* Timeline — full width at bottom */}
      <div style={{ flexShrink: 0, padding: "0 60px 36px" }}>
        <Timeline articles={articles} activeIndex={articleIndex} />
      </div>
    </AbsoluteFill>
  );
};
