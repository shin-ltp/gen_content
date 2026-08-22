import "./index.css";
import React, { useState, useEffect } from "react";
import { Composition, staticFile } from "remotion";
import {
  Episode,
  calcTotalFrames,
  FPS,
  MAIN_COVER_SEC,
  OVERVIEW_SEC,
  ENDING_SEC,
} from "./Composition";
import { EpisodeOverview } from "./EpisodeOverview";
import { MainCover } from "./MainCover";
import { ArticleCover } from "./ArticleCover";
import { Ending } from "./Ending";
import { VideoMetadata } from "./types";

const PREVIEW_DATA: VideoMetadata = {
  issueDate: "2026-02-21",
  episodeNum: 1,
  programTitle: "ザ・エコノミスト 2026-02-21",
  sections: [
    "The world this week",
    "International",
    "Leaders",
    "Finance & economics",
    "Briefing",
  ],
  articleCount: 6,
  estimatedMinutes: 61.2,
  coverImage: null,
  mainCover: {
    title: "ザ・エコノミスト 2026-02-21",
    sections: [
      "The world this week",
      "International",
      "Leaders",
      "Finance & economics",
      "Briefing",
    ],
    sectionLabels: ["今週の世界", "国際"],
    topArticles: [
      "今週の世界（ビジネス）",
      "トランプの特使たちは欧州を安心させることに失敗した",
      "自ら招いた苦境に陥るプーチン",
      "ロシア市場再開の「賞金」はどれほどのものか",
    ],
    firstArticleImage: "article_image_01.png",
  },
  articles: [
    {
      order: 1,
      originalTitle: "Business: The world this week",
      japaneseTitle: "今週の世界（ビジネス）",
      oneLineIntro:
        "ザッカーバーグ証言とメディア再編、激動の企業ニュースを追う。",
      summaryJa:
        "今週のビジネスニュースでは、メタ社のザッカーバーグCEOによる中毒性アルゴリズムに関する裁判証言や、ワーナー・ブラザースを巡る買収劇の新たな展開、バイエルによる巨額の和解案提示など、企業の法的・戦略的動きが注目されました。",
      section: "The world this week",
      sectionLabel: "今週の世界",
      isCoverStory: false,
      imagePath: "article_image_01.png",
      audioPath: null,
      durationSec: 779.3,
    },
    {
      order: 2,
      originalTitle: "Donald Trump's envoys failed to reassure Europe",
      japaneseTitle: "トランプの特使たちは欧州を安心させることに失敗した",
      oneLineIntro:
        "2026年、トランプ政権が欧州に迫る「核の傘」の厳しい条件。",
      summaryJa:
        "2026年2月、第2次トランプ政権下のミュンヘン安全保障会議において、ルビオ国務長官らが欧州諸国への再保証を試みた様子とその限界について論じた記事です。",
      section: "International",
      sectionLabel: "国際",
      isCoverStory: false,
      imagePath: "article_image_02.png",
      audioPath: null,
      durationSec: 598.5,
    },
    {
      order: 3,
      originalTitle: "Vladimir Putin is caught in a vice of his own making",
      japaneseTitle: "自ら招いた苦境に陥るプーチン",
      oneLineIntro:
        "平和さえも恐れるプーチン、彼を追い詰める万力の正体に迫る。",
      summaryJa:
        "2026年2月時点で4年目に突入したウクライナ戦争において、プーチン大統領が軍事的な勝利だけでなく、平和そのものをも恐れる「万力」のような窮地に陥っている現状を分析しています。",
      section: "Leaders",
      sectionLabel: "リーダーズ",
      isCoverStory: false,
      imagePath: "article_image_03.png",
      audioPath: null,
      durationSec: 707.4,
    },
    {
      order: 4,
      originalTitle: "How big is the prize of reopening Russia?",
      japaneseTitle: "ロシア市場再開の「賞金」はどれほどのものか",
      oneLineIntro:
        "トランプを狙う12兆ドルの誘惑、ロシアの提案に潜む危険な罠",
      summaryJa:
        "2026年、トランプ政権下の米国に対し、ロシアがウクライナ和平の対価として「12兆ドル」規模の経済取引を提示している現状とその実現可能性を分析した記事です。",
      section: "Finance & economics",
      sectionLabel: "金融・経済",
      isCoverStory: false,
      imagePath: "article_image_04.png",
      audioPath: null,
      durationSec: 822.5,
    },
    {
      order: 5,
      originalTitle: "How four years of war have changed Russia",
      japaneseTitle: "4年間の戦争はロシアをどう変えたか",
      oneLineIntro:
        "侵攻４年後のロシア、見せかけの好況と腐食する日常のリアル。",
      summaryJa:
        "ウクライナ侵攻から4年が経過した2026年2月、ロシア社会がどのように変容したかを描いた記事です。軍事支出による表面的な経済成長の裏で、インフラの劣化、資産の収奪、そして社会道徳の崩壊が進行している実態を詳述しています。",
      section: "Briefing",
      sectionLabel: "ブリーフィング",
      isCoverStory: false,
      imagePath: "article_image_05.png",
      audioPath: null,
      durationSec: 549.6,
    },
    {
      order: 6,
      originalTitle: "Don't go after the rich to fix broken budgets",
      japaneseTitle: "財政再建のために富裕層を狙い撃ちするな",
      oneLineIntro:
        "富裕層増税は救世主か？「ロビン・フッド国家」の不都合な真実",
      summaryJa:
        "米国や欧州で高まる「富裕層増税」の動きに対し、それが財政再建の切り札にはなり得ないとする分析記事です。著者は、富裕層への課税強化は期待するほどの税収を生まないばかりか、イノベーションを阻害し、経済全体に長期的な悪影響を及ぼすと指摘しています。",
      section: "Leaders",
      sectionLabel: "リーダーズ",
      isCoverStory: true,
      imagePath: "article_image_06.png",
      audioPath: null,
      durationSec: 596.2,
    },
  ],
  audioFiles: [
    "audio_01.mp3",
    "audio_02.mp3",
    "audio_03.mp3",
    "audio_04.mp3",
    "audio_05.mp3",
    "audio_06.mp3",
  ],
};

export const RemotionRoot: React.FC = () => {
  // public/remotion_input.json を優先（generate_video が書き出すパスと一致）。なければ PREVIEW_DATA
  const [props, setProps] = useState<VideoMetadata | null>(null);

  useEffect(() => {
    fetch(staticFile("remotion_input.json"))
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data: VideoMetadata) => {
        if (data?.issueDate && data?.articles?.length) {
          setProps(data);
          return;
        }
        setProps(PREVIEW_DATA);
      })
      .catch(() => setProps(PREVIEW_DATA));
  }, []);

  // JSON 読み込み完了まで Composition を出さない（PREVIEW_DATA で defaultProps が固まるのを防ぐ）
  if (props === null) {
    return null;
  }

  const totalFrames = calcTotalFrames(props.articles);
  const endingFrames = Math.round(ENDING_SEC * FPS);

  return (
    <>
      <Composition
        id="Episode"
        component={Episode}
        durationInFrames={totalFrames}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={props}
      />
      <Composition
        id="MainCover"
        component={(p: VideoMetadata) => <MainCover metadata={p} />}
        durationInFrames={Math.round(MAIN_COVER_SEC * FPS)}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={props}
      />
      <Composition
        id="EpisodeOverview"
        component={(p: VideoMetadata) => <EpisodeOverview metadata={p} />}
        durationInFrames={Math.round(OVERVIEW_SEC * FPS)}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={props}
      />
      <Composition
        id="ArticleCover"
        component={(p: VideoMetadata) => (
          <ArticleCover metadata={p} articleIndex={0} />
        )}
        durationInFrames={30 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={props}
      />
      <Composition
        id="Ending"
        component={Ending}
        durationInFrames={endingFrames}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
