import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { EpisodeInput } from "./types";

// End card fades in after the closing greeting has finished, while the
// ending BGM keeps playing to its tail fade.
export const EndCard: React.FC<{
  input: EpisodeInput;
  speechEndSec?: number;
}> = ({ input, speechEndSec }) => {
  const frame = useCurrentFrame();
  const startSec = speechEndSec ?? 0;
  const opacity = interpolate(
    frame,
    [startSec * 30, startSec * 30 + 30],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#FFFFFF",
        opacity,
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "\"Noto Sans JP\", sans-serif",
        color: "#10131F",
      }}
    >
      <Img src={staticFile("assets/logo-white-bk.png")} style={{ height: 140 }} />
      <div style={{ fontSize: 44, fontWeight: 900, marginTop: 30 }}>
        Smart Assets 米国株投資チャンネル
      </div>
      <div style={{ fontSize: 24, color: "rgba(16,19,31,.6)", marginTop: 14 }}>
        {input.dateJa} 配信
      </div>
      <div style={{ fontSize: 24, color: "rgba(16,19,31,.72)", marginTop: 42 }}>
        毎週月〜金の朝に更新。週末には「週間まとめ」も配信。
      </div>
      <div style={{ fontSize: 20, color: "rgba(16,19,31,.45)", marginTop: 46 }}>
        本番組は情報提供を目的としており、投資助言ではありません。
      </div>
    </AbsoluteFill>
  );
};
