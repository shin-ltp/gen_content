import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

const CHANNEL_LOGO_PATH = staticFile("channel_logo.png");

const FPS = 30;
const TOTAL_SEC = 33;
const SLIDE_DURATION = (TOTAL_SEC / 4) * FPS; // ~247.5 frames per slide
const FADE_FRAMES = 0.5 * FPS; // 0.5s fast fade

interface SlideProps {
  children: React.ReactNode;
  index: number;
}

const Slide: React.FC<SlideProps> = ({ children, index }) => {
  const frame = useCurrentFrame();
  const start = index * SLIDE_DURATION;
  const end = start + SLIDE_DURATION;

  if (frame < start - FADE_FRAMES || frame > end + FADE_FRAMES) return null;

  const opacity = interpolate(
    frame,
    [start, start + FADE_FRAMES, end - FADE_FRAMES, end],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      style={{
        opacity,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const Ending: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#f9fafb" }}>
      {/* Fixed header: Logo + GLOBAL CLIP */}
      <div
        style={{
          position: "absolute",
          top: 40,
          left: 60,
          display: "flex",
          alignItems: "center",
          gap: 16,
          zIndex: 10,
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

      {/* Slide 1: Thank you */}
      <Slide index={0}>
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            color: "#162557",
            textAlign: "center",
            lineHeight: 1.4,
          }}
        >
          最後までご視聴ありがとうございました。
        </div>
      </Slide>

      {/* Slide 2: Acknowledgements */}
      <Slide index={1}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 60,
          }}
        >
          <div
            style={{
              fontSize: 44,
              fontWeight: 700,
              color: "#6b7280",
              textAlign: "center",
              letterSpacing: 2,
            }}
          >
            Acknowledgements
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 36,
            }}
          >
            {[
              { label: "Articles", value: "The Economist", color: "#dc2626" },
              { label: "TTS", value: "Fish Audio", color: "#2563eb" },
              { label: "Video", value: "Remotion", color: "#059669" },
            ].map((item) => (
              <div
                key={item.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 48,
                }}
              >
                <div
                  style={{
                    fontSize: 36,
                    fontWeight: 700,
                    color: "#fff",
                    backgroundColor: item.color,
                    borderRadius: 8,
                    padding: "8px 28px",
                    minWidth: 200,
                    textAlign: "center",
                  }}
                >
                  {item.label}
                </div>
                <div
                  style={{
                    fontSize: 48,
                    fontWeight: 800,
                    color: "#111827",
                    textAlign: "left",
                  }}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Slide>

      {/* Slide 3: Subscribe */}
      <Slide index={2}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 36,
            maxWidth: 1400,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 60,
              fontWeight: 900,
              color: "#dc2626",
              lineHeight: 1.3,
            }}
          >
            いいねとチャンネル登録をお願いします！
          </div>
          <div
            style={{
              fontSize: 40,
              fontWeight: 600,
              color: "#374151",
              lineHeight: 1.6,
            }}
          >
            他のセクションも気になる方は
            <br />
            是非チャンネルのホーム画面からチェックしてください！
          </div>
        </div>
      </Slide>

      {/* Slide 4: Goodbye */}
      <Slide index={3}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 24,
          }}
        >
          <div
            style={{
              fontSize: 68,
              fontWeight: 900,
              color: "#162557",
              lineHeight: 1.4,
              textAlign: "center",
            }}
          >
            また来週お会いしましょう！
          </div>
          <div
            style={{
              fontSize: 48,
              fontWeight: 600,
              color: "#9ca3af",
              letterSpacing: 6,
            }}
          >
            ～さようなら～
          </div>
        </div>
      </Slide>
    </AbsoluteFill>
  );
};
