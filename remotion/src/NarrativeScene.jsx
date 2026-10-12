import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const labels = {
  event: 'WHAT CHANGED', comparison: 'THE NUMBERS', explanation: 'THE EXPLANATION',
  caveat: "WHAT WE DON'T KNOW", takeaway: 'THE TAKEAWAY',
};
const colors = {comparison: '#28c6d6', explanation: '#aab6ff', caveat: '#f4b449', takeaway: '#53d6a0'};
const fitted = new Map();
let canvas;

// Native fonts are provisioned by the renderer workflow. Measure bold text
// conservatively so the emphasized words also fit inside the available area.
const fit = (text, width, height, largest, lineHeight) => {
  const key = JSON.stringify([text, width, height, largest, lineHeight]);
  if (fitted.has(key)) return fitted.get(key);
  canvas ||= document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  let chosen = 18;
  for (let size = largest; size >= 18; size--) {
    ctx.font = `900 ${size}px "DejaVu Sans", "Liberation Sans", Arial, sans-serif`;
    let lines = 1;
    let line = '';
    for (const word of text.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (ctx.measureText(next).width <= width) line = next;
      else {
        if (line) lines++;
        const widthOfWord = ctx.measureText(word).width;
        lines += Math.max(0, Math.ceil(widthOfWord / width) - 1);
        line = word;
      }
    }
    if (lines * size * lineHeight <= height - 6) {chosen = size; break;}
  }
  fitted.set(key, chosen);
  return chosen;
};

const quantity = (text) => {
  const raw = text.toLowerCase().replace(/−/g, '-');
  const amount = parseFloat(raw.replace(/[$€£,]/g, ''));
  const factor = raw.includes('trillion') ? 1e12 : raw.includes('billion') ? 1e9 : raw.includes('million') ? 1e6 : raw.includes('thousand') ? 1e3 : 1;
  const currency = raw.match(/[$€£]/)?.[0];
  const unit = currency || (raw.includes('percent') || raw.includes('%') ? 'percent' : raw.includes('day') ? 'days' : raw.includes('cent') ? 'cents' : 'number');
  return {value: amount * factor, unit};
};

const Narration = ({scene, active, size}) => {
  const text = scene.narration;
  const at = scene.emphasis ? text.indexOf(scene.emphasis) : -1;
  return <div style={{fontSize: size, lineHeight: 1.3, fontWeight: 600, color: '#e7edf7', overflowWrap: 'anywhere'}}>
    {at < 0 ? text : <>{text.slice(0, at)}<span style={{color: active ? '#ffe45c' : '#ffffff', fontWeight: 900}}>{scene.emphasis}</span>{text.slice(at + scene.emphasis.length)}</>}
  </div>;
};

export const NarrativeScene = ({scene, index, total, isShorts, ticker, host, accent,
  franchiseName, closes, sessionOpen, sessionDate, showPriceContext}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = scene.start + frame / fps;
  const active = time >= scene.emphasisStart && time <= scene.emphasisEnd;
  const color = colors[scene.kind] || accent;
  const entrance = interpolate(frame, [0, 7], [18, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = interpolate(frame, [0, 7], [.7, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const comparison = scene.kind === 'comparison';
  const values = scene.figures.map(quantity);
  const comparable = comparison && values.length === 2 && values[0].unit !== 'number'
    && values.every((v) => Number.isFinite(v.value) && v.value >= 0 && v.unit === values[0].unit)
    && Math.max(...values.map((v) => v.value)) > 0;
  const reveal = interpolate(frame, [0, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const portrait = host && (scene.kind === 'event' || scene.kind === 'takeaway');
  const focusScale = active ? 1 + .025 * Math.sin(Math.min(Math.PI, (time - scene.emphasisStart) * 7)) : 1;
  const width = isShorts ? 840 : (portrait ? 1300 : 1500);
  const contextSpace = scene.kind === 'event' && showPriceContext ? (isShorts ? 100 : 75) : 0;
  const contentHeight = (isShorts ? 843 : 365) - contextSpace;
  const gap = isShorts ? 32 : 24;
  const figureHeight = isShorts ? 250 : 175;
  const focusHeight = isShorts ? 190 : 100;
  const bodyHeight = contentHeight - (comparison ? figureHeight + gap : scene.emphasis ? focusHeight + gap : 0);
  const bodySize = fit(scene.narration, width, bodyHeight, isShorts ? 59 : 48, 1.3);
  const focusSize = fit(scene.emphasis || '', width - 60, focusHeight - (isShorts ? 56 : 36), isShorts ? 51 : 42, 1.18);
  return <div style={{position: 'absolute', ...(isShorts
    ? {left: 60, top: 185, width: 960, height: 1270}
    : {left: 130, top: 110, width: 1660, height: 730}),
    boxSizing: 'border-box', padding: isShorts ? '42px 48px' : '38px 60px', overflow: 'hidden',
    background: `linear-gradient(145deg, ${color}16, #0e192a 55%)`, borderRadius: 30,
    border: `2px solid ${color}77`, borderLeft: `12px solid ${color}`,
    boxShadow: '0 30px 100px #0009', opacity, transform: `translateY(${entrance}px)`}}>
    <div style={{fontSize: isShorts ? 23 : 24, color, fontWeight: 800, letterSpacing: 1.2,
      paddingBottom: 25, borderBottom: `2px solid ${color}44`}}>DENIZ / US STOCK MARKET DAILY</div>
    <div style={{position: 'absolute', top: isShorts ? 42 : 38, right: 48,
      fontSize: isShorts ? 25 : 24, color: '#9fb3c8'}}>{index + 1} / {total}</div>
    <div style={{marginTop: 30, display: 'flex', alignItems: 'center', gap: 25}}>
      <div style={{fontSize: isShorts ? 70 : 62, fontWeight: 900, lineHeight: 1}}>{ticker}</div>
      {franchiseName && <div style={{fontSize: isShorts ? 20 : 25, color: '#9fb3c8'}}>{franchiseName}</div>}
    </div>
    {portrait && <Img src={staticFile(host)} style={{position: 'absolute', right: isShorts ? 45 : 65,
      top: isShorts ? 110 : 160, width: isShorts ? 125 : 140, height: isShorts ? 175 : 185,
      objectFit: 'contain'}} />}
    <div style={{marginTop: isShorts ? 40 : 25, fontSize: isShorts ? 30 : 28,
      fontWeight: 900, letterSpacing: 1.7, color}}>{labels[scene.kind]}</div>
    <div style={{position: 'absolute', left: isShorts ? 48 : 60, right: isShorts ? 48 : 60,
      top: isShorts ? 335 : 270, bottom: (isShorts ? 92 : 95) + contextSpace,
      display: 'flex', flexDirection: 'column', gap, maxWidth: !isShorts && portrait ? 1300 : undefined}}>
      {comparison ? <div style={{display: 'flex', gap: 24, height: figureHeight, flexShrink: 0}}>
        {scene.figures.map((figure, i) => <div key={i} style={{flex: 1, minWidth: 0, padding: isShorts ? '32px 20px' : '24px',
          boxSizing: 'border-box',
          borderRadius: 22, border: `2px solid ${color}77`, background: '#091625', color,
          fontSize: fit(figure, isShorts ? 370 : 690, figureHeight - (isShorts ? 100 : 85), isShorts ? 72 : 80, 1.15),
          fontWeight: 900, lineHeight: 1.15, overflowWrap: 'anywhere', transform: `scale(${focusScale})`}}>
          {figure}
          {comparable && <div style={{height: 9, marginTop: 26, borderRadius: 5, background: '#25374a'}}>
            <div style={{height: '100%', borderRadius: 5, background: color,
              width: `${100 * reveal * values[i].value / Math.max(...values.map((v) => v.value))}%`}} />
          </div>}
        </div>)}
      </div> : null}
      <div style={{height: bodyHeight, flexShrink: 0}}><Narration scene={scene} active={active} size={bodySize} /></div>
      {!comparison && scene.emphasis && <div style={{height: focusHeight, boxSizing: 'border-box', flexShrink: 0,
        padding: isShorts ? '28px 30px' : '18px 28px', borderRadius: 20,
        background: `${color}16`, borderLeft: `5px solid ${color}`, color,
        fontSize: focusSize, fontWeight: 900, lineHeight: 1.18,
        transformOrigin: 'left center', transform: `scale(${focusScale})`}}>{scene.emphasis}</div>}
    </div>
    {scene.kind === 'event' && showPriceContext && <div style={{position: 'absolute', bottom: 92, left: isShorts ? 48 : 60,
      right: 48, color: '#9fb3c8', fontSize: isShorts ? 21 : 23, lineHeight: 1.5}}>
      PRICE CONTEXT · {sessionDate}<br />SESSION OPEN {sessionOpen.toFixed(2)} · LAST {closes[closes.length - 1].toFixed(2)}
    </div>}
    <div style={{position: 'absolute', bottom: 38, left: 48, right: 48, display: 'flex', gap: 10}}>
      {Array.from({length: total}, (_, i) => <div key={i} style={{height: 5, flex: 1, borderRadius: 3,
        background: i <= index ? color : '#29364a'}} />)}
    </div>
  </div>;
};

export const StoryCaptions = ({words, scenes, isShorts}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  const scene = scenes.find((s) => time >= s.start && time < s.end);
  if (!scene) return null;
  const localWords = words.filter((w) => w.start >= scene.start && w.start < scene.end);
  let active = localWords.findIndex((w) => time >= w.start && time < w.end);
  if (active < 0) active = localWords.findLastIndex((w) => time >= w.end && time < w.end + .22);
  if (active < 0) return null;
  const group = isShorts ? 3 : 5;
  const start = Math.floor(active / group) * group;
  return <div style={{position: 'absolute', left: isShorts ? 85 : 170, right: isShorts ? 85 : 170,
    bottom: isShorts ? 245 : 70, minHeight: isShorts ? 125 : 95,
    display: 'flex', justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap', gap: 16,
    textAlign: 'center', fontSize: isShorts ? 66 : 52, fontWeight: 900, lineHeight: 1.1,
    textShadow: '0 4px 10px #000, 0 0 4px #000'}}>
    {localWords.slice(start, start + group).map((word, i) => <span key={`${start}-${i}`}
      style={{color: start + i === active ? '#ffe45c' : '#ffffff'}}>{word.text.toUpperCase()}</span>)}
  </div>;
};
