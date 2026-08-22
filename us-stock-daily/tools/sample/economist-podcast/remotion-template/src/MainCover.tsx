import React, { useState } from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { VideoMetadata } from "./types";
import { ARTICLE_COLORS } from "./constants";

const CHANNEL_LOGO_PATH = staticFile("channel_logo.png");
const OVERLAY_LOGO_PATH = staticFile("logo_red.svg");

export const MainCover: React.FC<{ metadata: VideoMetadata }> = ({ metadata }) => {
  const { mainCover, issueDate, episodeNum, coverImage } = metadata;
  const sectionLabels = mainCover.sectionLabels ?? [];
  const [rightImageError, setRightImageError] = useState(false);

  // Episode 1 with cover.jpg: show magazine cover directly
  // Other episodes: show article image with logo overlay
  const useCover = episodeNum === 1 && !!coverImage;
  const rightImageRaw = useCover ? coverImage : mainCover.firstArticleImage;
  const rightImage = rightImageRaw ? staticFile(rightImageRaw) : null;
  const showRightImage = rightImage && !rightImageError;

  return (
    <AbsoluteFill style={{ display: "flex", flexDirection: "row", backgroundColor: "#fff" }}>
      {/* Left Panel */}
      <div style={{
        display: "flex",
        flexDirection: "column",
        width: "58%",
        height: "100%",
        padding: "40px 50px 36px",
        backgroundColor: "#f9fafb",
        borderRight: "1px solid #e5e7eb",
      }}>
        {/* Channel Logo + Name */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
          <div style={{ width: 110, height: 110, flexShrink: 0 }}>
            <Img
              src={CHANNEL_LOGO_PATH}
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
          </div>
          <span style={{ fontSize: 44, fontWeight: 900, color: "#162557", letterSpacing: 2 }}>
            GLOBAL CLIP
          </span>
        </div>

        {/* Program Title & Issue Date */}
        <div style={{ marginTop: 20, flexShrink: 0, display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
          <span style={{ fontSize: 62, fontWeight: 900, color: "#dc2626", lineHeight: 1.2 }}>
            ザ・エコノミスト
          </span>
          <span style={{ fontSize: 44, fontWeight: 800, color: "#1f2937", lineHeight: 1.2 }}>
            {issueDate}
          </span>
        </div>

        {/* Article Titles */}
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: 22,
          marginTop: 24,
          width: "100%",
          flex: 1,
          justifyContent: "center",
        }}>
          {mainCover.topArticles.map((title, index) => (
            <div
              key={index}
              style={{
                fontSize: 48,
                fontWeight: 800,
                lineHeight: 1.25,
                color: "#111827",
                borderLeft: `6px solid ${ARTICLE_COLORS[index % ARTICLE_COLORS.length]}`,
                paddingLeft: 20,
                paddingTop: 3,
                paddingBottom: 3,
              }}
            >
              {title}
            </div>
          ))}
        </div>

        {/* Section Labels */}
        {sectionLabels.length > 0 && (
          <div style={{ display: "flex", gap: 14, flexShrink: 0, marginTop: 12 }}>
            {sectionLabels.map((label, i) => (
              <div
                key={i}
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: "#fff",
                  backgroundColor: "#162557",
                  borderRadius: 6,
                  padding: "6px 20px",
                  letterSpacing: 1,
                }}
              >
                {label}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right Panel */}
      <div style={{
        position: "relative",
        width: "42%",
        height: "100%",
        backgroundColor: "#f9fafb",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        {showRightImage ? (
          <Img
            src={rightImage}
            onError={() => setRightImageError(true)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
            }}
          />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#9ca3af", fontSize: 24 }}>
            No Image Available
          </div>
        )}

        {!useCover && (
          <>
            <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.4), transparent)", pointerEvents: "none" }} />
            <div style={{ position: "absolute", top: 40, left: 40, width: 256, filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.4))" }}>
              <Img
                src={OVERLAY_LOGO_PATH}
                style={{ width: "100%", height: "auto" }}
              />
            </div>
          </>
        )}
      </div>
    </AbsoluteFill>
  );
};
