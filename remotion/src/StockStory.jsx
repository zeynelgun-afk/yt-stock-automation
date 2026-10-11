import React from 'react';
import {Video} from '@remotion/media';
import {
  AbsoluteFill, Audio, Img, Sequence, interpolate,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

const palette = {
  congress_trade: '#d85432', insider_watch: '#d85432',
  earnings_shock: '#f4b449', analyst_shock: '#28c6d6',
};

const pctText = (value) => {
  const raw = String(value ?? '0').replace(/%/g, '');
  return `${raw.startsWith('-') || raw.startsWith('+') ? '' : '+'}${raw}%`;
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

const Chart = ({closes, sessionOpen, ticker, date, accent, isShorts}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const low = Math.min(...closes);
  const high = Math.max(...closes);
  const pad = (high - low) * .09 || Math.abs(high) * .01 || 1;
  const span = high - low + 2 * pad;
  const x = (i) => 40 + (i / (closes.length - 1)) * 720;
  const y = (v) => 440 - ((v - low + pad) / span) * 345;
  const points = closes.map((value, i) => `${x(i)},${y(value)}`).join(' ');
  const reveal = 1 - Math.pow(1 - Math.min(1, frame / Math.max(1, Math.min(durationInFrames * .8, 60 * fps))), 2);
  const lengths = closes.slice(1).map((value, i) => Math.hypot(x(i + 1) - x(i), y(value) - y(closes[i])));
  const totalLength = lengths.reduce((sum, length) => sum + length, 0);
  let remaining = totalLength * reveal;
  let dotX = x(0);
  let dotY = y(closes[0]);
  for (let i = 0; i < lengths.length; i++) {
    const fraction = Math.min(1, remaining / lengths[i]);
    dotX = x(i) + (x(i + 1) - x(i)) * fraction;
    dotY = y(closes[i]) + (y(closes[i + 1]) - y(closes[i])) * fraction;
    remaining -= lengths[i];
    if (remaining <= 0) break;
  }
  const up = closes[closes.length - 1] >= sessionOpen;
  const color = up ? '#22c55e' : '#ef4444';
  return <div style={{position: 'absolute', ...(isShorts ? {left: 35, right: 35, bottom: 48, height: 475} : {left: 780, right: 40, top: 120, bottom: 52}),
    border: `2px solid ${accent}`, borderRadius: 24, background: '#0a1728', overflow: 'hidden'}}>
    <div style={{position: 'absolute', zIndex: 2, top: 20, left: 26, right: 26, display: 'flex', justifyContent: 'space-between', color: '#dfe9f5', fontSize: 25, fontWeight: 800}}>
      <span>{ticker} · INTRADAY</span><span>{date || 'LIVE SESSION'}</span>
    </div>
    <svg viewBox="0 0 800 500" preserveAspectRatio="none" style={{width: '100%', height: '100%'}}>
      {[160, 260, 360].map((line) => <line key={line} x1="35" y1={line} x2="765" y2={line} stroke="#25374a" strokeWidth="2" />)}
      <polyline points={points} fill="none" stroke={color} strokeWidth="20" opacity=".13" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1 - reveal} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1 - reveal} />
      <circle cx={dotX} cy={dotY} r={9 + 2 * Math.sin(frame * .25)} fill={color} />
      <text x="40" y="475" fill="#9fb3c8" fontSize="25">OPEN {sessionOpen.toFixed(2)}</text>
      <text x="760" y="475" textAnchor="end" fill={color} fontSize="28" fontWeight="800">LAST {closes[closes.length - 1].toFixed(2)}</text>
    </svg>
  </div>;
};

const Captions = ({words, isShorts}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  const active = words.findIndex((word) => time >= word.start && time < word.end);
  if (active < 0) return null;
  const groupSize = isShorts ? 3 : 5;
  const start = Math.floor(active / groupSize) * groupSize;
  return <div style={{position: 'absolute', left: isShorts ? 85 : 175, right: isShorts ? 85 : 175,
    bottom: isShorts ? 235 : 45, minHeight: isShorts ? 120 : 90,
    display: 'flex', justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap', gap: 18,
    textAlign: 'center', fontSize: isShorts ? 80 : 55, fontWeight: 900, lineHeight: 1.05,
    textShadow: '0 4px 10px #000, 0 0 4px #000'}}>
    {words.slice(start, start + groupSize).map((word, offset) => <span key={`${start}-${offset}`} style={{color: start + offset === active ? '#ffe45c' : '#ffffff'}}>{word.text.toUpperCase()}</span>)}
  </div>;
};

export const StockStory = (props) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {isShorts, ticker, title, heroNumber, heroLabel, franchise, franchiseName,
    changePct, closes, sessionOpen, sessionDate, words, backgrounds, host, music, whoosh, audio} = props;
  const accent = palette[franchise] || '#28c6d6';
  const change = pctText(changePct);
  const positive = !change.startsWith('-');
  const card = isShorts ? {left: 60, top: 185, width: 960, height: 1330} : {left: 160, top: 100, width: 1600, height: 785};
  const entrance = interpolate(frame, [0, 18], [28, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{fontFamily: 'DejaVu Sans, Liberation Sans, Arial, sans-serif', color: '#f8fafc'}}>
    <Background clips={backgrounds} theme={franchise} />
    <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(7,16,30,.15), rgba(7,16,30,.55))'}} />
    <div style={{position: 'absolute', ...card, boxSizing: 'border-box', overflow: 'hidden',
      background: 'rgba(14,25,42,.95)', borderRadius: 30, borderLeft: `14px solid ${accent}`,
      boxShadow: '0 30px 100px #0009', transform: `translateY(${entrance}px)`}}>
      <div style={{position: 'absolute', top: 32, left: 38, right: 38, paddingBottom: 20,
        borderBottom: `2px solid ${accent}55`, color: accent, fontWeight: 900, fontSize: isShorts ? 26 : 27,
        letterSpacing: 1.5}}>DENIZ / US STOCK MARKET DAILY {franchiseName ? `/ ${franchiseName.toUpperCase()}` : ''}</div>
      {host && <Img src={staticFile(host)} style={{position: 'absolute', top: isShorts ? 140 : 145,
        right: isShorts ? 35 : 845, width: isShorts ? 220 : 155,
        height: isShorts ? 300 : 210, objectFit: 'contain', objectPosition: 'top right'}} />}
      <div style={{position: 'absolute', top: isShorts ? 148 : 145, left: 40, right: isShorts ? 300 : 1000,
        fontSize: isShorts ? 105 : 100, fontWeight: 900, lineHeight: 1, whiteSpace: 'nowrap'}}>{ticker}</div>
      <div style={{position: 'absolute', top: isShorts ? 265 : 255, left: 44, color: positive ? '#22c55e' : '#ef4444',
        fontSize: isShorts ? 56 : 54, fontWeight: 900}}>{change}</div>
      <div style={{position: 'absolute', top: isShorts ? 335 : 321, left: 44, color: '#9fb3c8', fontSize: 22,
        letterSpacing: 1.5}}>SINCE SESSION OPEN</div>
      {heroNumber && <>
        <div style={{position: 'absolute', top: isShorts ? 408 : 395, left: 42, right: isShorts ? 40 : 900,
          color: '#9fb3c8', fontSize: isShorts ? 31 : 27, fontWeight: 800}}>{heroLabel.toUpperCase()}</div>
        <div style={{position: 'absolute', top: isShorts ? 452 : 432, left: 40, right: isShorts ? 38 : 880,
          fontSize: isShorts ? (heroNumber.length > 11 ? 95 : 135) : (heroNumber.length > 9 ? 74 : 110),
          fontWeight: 900, lineHeight: 1.05, overflowWrap: 'anywhere'}}>{heroNumber}</div>
      </>}
      <div style={{position: 'absolute', top: isShorts ? (heroNumber ? 645 : 425) : (heroNumber ? 575 : 420),
        left: 44, right: isShorts ? 44 : 890, color: '#d4e1ef', fontSize: isShorts ? 42 : 35,
        lineHeight: 1.27, fontWeight: 600, overflow: 'hidden', maxHeight: isShorts ? 140 : 155}}>{title}</div>
      <Chart closes={closes} sessionOpen={sessionOpen} ticker={ticker} date={sessionDate} accent={accent} isShorts={isShorts} />
    </div>
    <Captions words={words} isShorts={isShorts} />
    {audio && <Audio src={staticFile(audio)} />}
    {music && <Audio src={staticFile(music)} loop volume={0.08} />}
    {whoosh && <Sequence from={4 * fps}><Audio src={staticFile(whoosh)} volume={0.45} /></Sequence>}
  </AbsoluteFill>;
};
