import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { MainCover } from "./MainCover";
import { EpisodeOverview } from "./EpisodeOverview";
import { ArticleCover } from "./ArticleCover";
import { Ending } from "./Ending";
import { VideoMetadata } from "./types";

export const FPS = 30;
export const MAIN_COVER_SEC = 41;
export const OVERVIEW_SEC = 60;
export const ENDING_SEC = 33;

const FADE_FRAMES = Math.round(0.5 * FPS); // 0.5s cross-dissolve

interface FadeProps {
  children: React.ReactNode;
  durationInFrames: number;
  fadeIn?: boolean;
  fadeOut?: boolean;
}

const Fade: React.FC<FadeProps> = ({
  children,
  durationInFrames,
  fadeIn = true,
  fadeOut = true,
}) => {
  const frame = useCurrentFrame();
  let opacity = 1;
  if (fadeIn) {
    opacity = Math.min(
      opacity,
      interpolate(frame, [0, FADE_FRAMES], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    );
  }
  if (fadeOut) {
    opacity = Math.min(
      opacity,
      interpolate(
        frame,
        [durationInFrames - FADE_FRAMES, durationInFrames],
        [1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      ),
    );
  }
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

export function calcTotalFrames(
  articles: { durationSec: number }[],
): number {
  const totalSec = articles.reduce((sum, a) => sum + a.durationSec, 0);
  return Math.ceil(totalSec * FPS);
}

export const Episode: React.FC<VideoMetadata> = (props) => {
  const { articles, audioFiles } = props;

  // Cumulative audio end times (seconds)
  const cumulativeSec: number[] = [];
  let cumSum = 0;
  for (const article of articles) {
    cumSum += article.durationSec;
    cumulativeSec.push(cumSum);
  }

  const totalFrames = Math.ceil(cumSum * FPS);
  const mainCoverEnd = Math.round(MAIN_COVER_SEC * FPS);
  const overviewEnd = Math.round((MAIN_COVER_SEC + OVERVIEW_SEC) * FPS);
  const endingStart = totalFrames - Math.round(ENDING_SEC * FPS);

  // Audio cumulative start frames
  const audioCumStart: number[] = [];
  let audioOffset = 0;
  for (const article of articles) {
    audioCumStart.push(audioOffset);
    audioOffset += Math.round(article.durationSec * FPS);
  }

  // Article cover visual timing based on cumulative audio end times
  const articleVisuals = articles
    .map((_, index) => {
      const from =
        index === 0
          ? overviewEnd
          : Math.round(cumulativeSec[index - 1] * FPS);
      const to = Math.min(
        Math.round(cumulativeSec[index] * FPS),
        endingStart,
      );
      return { from, logicalDuration: to - from, index };
    })
    .filter((s) => s.logicalDuration > 0);

  return (
    <AbsoluteFill style={{ backgroundColor: "#fff" }}>
      {/* Audio tracks — sequenced by article order */}
      {audioFiles.map((file, i) =>
        i < articles.length ? (
          <Sequence
            key={`audio-${i}`}
            from={audioCumStart[i]}
            durationInFrames={Math.round(articles[i].durationSec * FPS)}
          >
            <Audio src={staticFile(file)} />
          </Sequence>
        ) : null,
      )}

      {/* MainCover — no fade-in, cross-dissolve out */}
      <Sequence
        from={0}
        durationInFrames={mainCoverEnd + FADE_FRAMES}
        name="MainCover"
      >
        <Fade
          durationInFrames={mainCoverEnd + FADE_FRAMES}
          fadeIn={false}
          fadeOut
        >
          <MainCover metadata={props} />
        </Fade>
      </Sequence>

      {/* EpisodeOverview — cross-dissolve in/out */}
      <Sequence
        from={mainCoverEnd}
        durationInFrames={overviewEnd - mainCoverEnd + FADE_FRAMES}
        name="EpisodeOverview"
      >
        <Fade
          durationInFrames={overviewEnd - mainCoverEnd + FADE_FRAMES}
          fadeIn
          fadeOut
        >
          <EpisodeOverview metadata={props} />
        </Fade>
      </Sequence>

      {/* Article Covers — each cross-dissolves into the next */}
      {articleVisuals.map((seq) => {
        const seqDuration = seq.logicalDuration + FADE_FRAMES;
        return (
          <Sequence
            key={seq.index}
            from={seq.from}
            durationInFrames={seqDuration}
            name={`Article-${seq.index + 1}`}
          >
            <Fade durationInFrames={seqDuration} fadeIn fadeOut>
              <ArticleCover metadata={props} articleIndex={seq.index} />
            </Fade>
          </Sequence>
        );
      })}

      {/* Ending — cross-dissolve in, no fade-out (internal slides handle it) */}
      <Sequence
        from={endingStart}
        durationInFrames={totalFrames - endingStart}
        name="Ending"
      >
        <Fade
          durationInFrames={totalFrames - endingStart}
          fadeIn
          fadeOut={false}
        >
          <Ending />
        </Fade>
      </Sequence>
    </AbsoluteFill>
  );
};
