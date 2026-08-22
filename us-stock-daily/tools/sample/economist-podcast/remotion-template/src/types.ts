export interface Article {
  order: number;
  originalTitle: string;
  japaneseTitle: string;
  oneLineIntro: string;
  summaryJa: string;
  section: string;
  sectionLabel: string;
  isCoverStory: boolean;
  imagePath: string | null;
  audioPath: string | null;
  durationSec: number;
}

export interface MainCoverProps {
  title: string;
  sections: string[];
  sectionLabels: string[];
  topArticles: string[];
  firstArticleImage: string | null;
}

export interface VideoMetadata {
  issueDate: string;
  episodeNum: number;
  programTitle: string;
  sections: string[];
  articleCount: number;
  estimatedMinutes: number;
  coverImage: string | null;
  mainCover: MainCoverProps;
  articles: Article[];
  audioFiles: string[];
}
