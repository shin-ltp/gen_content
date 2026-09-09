import React, { useEffect, useState } from "react";
import { Composition, getInputProps, staticFile } from "remotion";
import { Episode, totalFramesOf } from "./Episode";
import { FPS, HEIGHT, WIDTH } from "./constants";
import { EpisodeInput, SegmentInput } from "./types";

// Minimal fallback so `npm run dev` works before prepare_remotion.py runs.
const PLACEHOLDER: SegmentInput = {
  order: 0,
  id: "S00-title",
  slide: "s0",
  image: null,
  audio: null,
  durationSec: 10,
  timingSource: "estimated",
  title: "Remotion 环境 OK（待 prepare_remotion.py 注入）",
  corner: "OP",
  sting: false,
  sentences: [],
};

const PREVIEW: EpisodeInput = {
  episode: "preview",
  dateJa: "プレビュー",
  fps: FPS,
  width: WIDTH,
  height: HEIGHT,
  bgmBed: null,
  stingFile: null,
  segments: [PLACEHOLDER],
};

// CLI renders pass props synchronously via --props; Studio has none
// until remotion_input.json is fetched, then it re-registers.
const initialInput = (): EpisodeInput => {
  try {
    const p = getInputProps() as Partial<EpisodeInput>;
    if (p && Array.isArray(p.segments) && p.segments.length) {
      return p as EpisodeInput;
    }
  } catch {
    /* no props provided */
  }
  return PREVIEW;
};

export const RemotionRoot: React.FC = () => {
  const [input, setInput] = useState<EpisodeInput>(initialInput);

  useEffect(() => {
    if (input !== PREVIEW) {
      return;
    }
    fetch(staticFile("remotion_input.json"))
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data: EpisodeInput) => {
        if (data?.segments?.length) {
          setInput(data);
        }
      })
      .catch(() => undefined);
  }, [input]);

  return (
    <Composition
      id="Episode"
      component={Episode as unknown as React.FC<Record<string, unknown>>}
      durationInFrames={totalFramesOf(
        input.segments,
        input.fps,
        input.stingFrames,
      )}
      fps={input.fps}
      width={input.width}
      height={input.height}
      defaultProps={input as unknown as Record<string, unknown>}
      calculateMetadata={({ props }) => {
        const p = props as unknown as EpisodeInput;
        return {
          durationInFrames: totalFramesOf(
            p.segments,
            p.fps,
            p.stingFrames,
          ),
          fps: p.fps,
          width: p.width,
          height: p.height,
        };
      }}
    />
  );
};
