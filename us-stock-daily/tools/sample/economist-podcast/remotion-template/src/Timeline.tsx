import React from "react";
import { Article } from "./types";
import { ARTICLE_COLORS } from "./constants";

interface TimelineProps {
  articles: Article[];
  activeIndex?: number;
  height?: number;
}

export const Timeline: React.FC<TimelineProps> = ({
  articles,
  activeIndex,
  height = 28,
}) => {
  const totalDuration = articles.reduce((sum, a) => sum + a.durationSec, 0);
  if (totalDuration === 0) return null;

  return (
    <div style={{
      display: "flex",
      width: "100%",
      height,
      borderRadius: height / 2,
      overflow: "hidden",
      backgroundColor: "#e5e7eb",
      flexShrink: 0,
    }}>
      {articles.map((article, i) => {
        const widthPct = (article.durationSec / totalDuration) * 100;
        const color = ARTICLE_COLORS[i % ARTICLE_COLORS.length];
        const isActive = activeIndex === i;

        return (
          <div
            key={article.order}
            style={{
              width: `${widthPct}%`,
              height: "100%",
              backgroundColor: color,
              opacity: activeIndex !== undefined && !isActive ? 0.35 : 1,
              borderRight:
                i < articles.length - 1
                  ? "2px solid rgba(255,255,255,0.6)"
                  : "none",
              transition: "opacity 0.3s",
            }}
          />
        );
      })}
    </div>
  );
};
