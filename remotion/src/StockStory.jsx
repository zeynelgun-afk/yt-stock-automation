import React from 'react';
import {Video} from '@remotion/media';
import {
  AbsoluteFill, Audio, Sequence, interpolate,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import {NarrativeScene, StoryCaptions} from './NarrativeScene';

const palette = {
  congress_trade: '#d85432', insider_watch: '#d85432',
  earnings_shock: '#f4b449', analyst_shock: '#28c6d6',
};

const themes = {
  congress_trade: '#744032', insider_watch: '#744032',
  earnings_shock: '#6b4b20', analyst_shock: '#145466',
};

const Background = ({clips, theme}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();
  if (!clips.length) {
    const glow = themes[theme] || '#1e3a5f';
    const drift = Math.sin(frame / 95) * 12;
    return <AbsoluteFill style={{background: `radial-gradient(circle at ${75 + drift}% 20%, ${glow} 0, #10192a 55%, #0a1322 100%)`}} />;
  }
  const segment = durationInFrames / clips.length;
  return <AbsoluteFill style={{overflow: 'hidden', background: '#0a1322'}}>
    {clips.map((clip, index) => {
      const start = Math.max(0, Math.floor(index * segment) - fps);
      const end = Math.min(durationInFrames, Math.ceil((index + 1) * segment) + fps);
      const fadeIn = index === 0 ? 1 : interpolate(frame, [index * segment - fps, index * segment], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      const fadeOut = index === clips.length - 1 ? 1 : interpolate(frame, [(index + 1) * segment, (index + 1) * segment + fps], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      return <Sequence key={clip} from={start} durationInFrames={Math.max(1, end - start)}>
        <AbsoluteFill style={{opacity: Math.min(fadeIn, fadeOut), overflow: 'hidden'}}>
          <Video src={staticFile(clip)} loop muted style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(6px) saturate(.8) brightness(.45)', transform: 'scale(1.06)'}} />
        </AbsoluteFill>
      </Sequence>;
    })}
    <AbsoluteFill style={{background: 'linear-gradient(145deg, rgba(8,18,35,.5), rgba(8,18,35,.78))'}} />
  </AbsoluteFill>;
};

export const StockStory = (props) => {
  const {fps, durationInFrames} = useVideoConfig();
  const {isShorts, ticker, franchise, franchiseName, closes, sessionOpen,
    sessionDate, words, scenes, backgrounds, host, music, whoosh, audio} = props;
  const accent = palette[franchise] || '#28c6d6';
  return <AbsoluteFill style={{fontFamily: 'DejaVu Sans, Liberation Sans, Arial, sans-serif', color: '#f8fafc'}}>
    <Background clips={backgrounds} theme={franchise} />
    <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(7,16,30,.15), rgba(7,16,30,.55))'}} />
    {scenes.map((scene, index) => {
      const from = Math.floor(scene.start * fps);
      const to = index === scenes.length - 1 ? durationInFrames : Math.floor(scene.end * fps);
      return <Sequence key={index} from={from} durationInFrames={Math.max(1, to - from)}>
        <NarrativeScene scene={scene} index={index} total={scenes.length} isShorts={isShorts}
          ticker={ticker} host={host} accent={accent} franchiseName={franchiseName}
          closes={closes} sessionOpen={sessionOpen} sessionDate={sessionDate}
          showPriceContext={franchise === 'market_close'} />
      </Sequence>;
    })}
    <StoryCaptions words={words} scenes={scenes} isShorts={isShorts} />
    {audio && <Audio src={staticFile(audio)} />}
    {music && <Audio src={staticFile(music)} loop volume={0.08} />}
    {whoosh && <Sequence from={4 * fps}><Audio src={staticFile(whoosh)} volume={0.45} /></Sequence>}
  </AbsoluteFill>;
};
