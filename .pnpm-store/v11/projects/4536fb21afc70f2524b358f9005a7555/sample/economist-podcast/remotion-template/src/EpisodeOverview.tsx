import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { VideoMetadata } from "./types";
import { ARTICLE_COLORS } from "./constants";
import { Timeline } from "./Timeline";

const CHANNEL_LOGO_PATH = staticFile("channel_logo.png");

export const EpisodeOverview: React.FC<{ metadata: VideoMetadata }> = ({
  metadata,
}) => {
  const { articles, issueDate } = metadata;

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#f9fafb",
        padding: "40px 60px 44px",
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

      {/* Program Title & Issue Date */}
      <div
        style={{
          marginTop: 16,
          flexShrink: 0,
          display: "flex",
          alignItems: "baseline",
          justifyContent: "center",
          gap: 12,
        }}
      >
        <span
          style={{
            fontSize: 52,
            fontWeight: 900,
            color: "#dc2626",
            lineHeight: 1.2,
          }}
        >
          ザ・エコノミスト
        </span>
        <span
          style={{
            fontSize: 44,
            fontWeight: 800,
            color: "#1f2937",
            lineHeight: 1.2,
          }}
        >
          {issueDate}
        </span>
      </div>

      {/* Article Intro List — centered, 70% of viewport height */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            height: "70%",
            width: "85%",
          }}
        >
          {articles.map((article, index) => (
            <div
              key={article.order}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 18,
              }}
            >
              <div
                style={{
                  flexShrink: 0,
                  width: 52,
                  height: 52,
                  borderRadius: "50%",
                  backgroundColor:
                    ARTICLE_COLORS[index % ARTICLE_COLORS.length],
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#fff",
                  fontSize: 28,
                  fontWeight: 900,
                  marginTop: 4,
                }}
              >
                {article.order}
              </div>
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: 44,
                    fontWeight: 800,
                    lineHeight: 1.25,
                    color: "#111827",
                    borderLeft: `6px solid ${ARTICLE_COLORS[index % ARTICLE_COLORS.length]}`,
                    paddingLeft: 18,
                  }}
                >
                  {article.oneLineIntro}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div style={{ flexShrink: 0, marginTop: 20 }}>
        <Timeline articles={articles} />
      </div>
    </AbsoluteFill>
  );
};
