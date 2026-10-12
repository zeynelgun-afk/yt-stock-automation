import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {StockStory} from './StockStory';

const Root = () => (
  <Composition
    id="StockStory"
    component={StockStory}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={1200}
    defaultProps={{
      title: '', ticker: 'TEST', changePct: '0', franchise: '', franchiseName: '',
      heroNumber: '', heroLabel: '', isShorts: true, closes: [100, 101],
      sessionOpen: 100, sessionDate: '', words: [], audio: '',
      backgrounds: [], scenes: [], host: null, music: null, whoosh: null,
    }}
  />
);

registerRoot(Root);
