"""Daily read-only experiment report, independent of LLM/voice provider budgets.

YouTube Analytics has day-level Pacific windows, not an exact hourly 72h slice.
Compare the first three COMPLETE Pacific dates after each publication instead.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from editorial_policy import EXPERIMENT_ID
from publication_history import fetch_upload_history, parse_time, youtube_credentials

STARTED_AT = '2026-09-16T11:24:59Z'
PACIFIC = ZoneInfo('America/Los_Angeles')
METRICS = 'views,engagedViews,averageViewDuration,averageViewPercentage,subscribersGained'


def measurement_window(published_at):
    publication_day = parse_time(published_at).astimezone(PACIFIC).date()
    start = publication_day + timedelta(days=1)
    return start, start + timedelta(days=2)


def summarize(rows):
    complete = [r for r in rows if r['status'] == 'available']
    engaged = sum(r['metrics']['engagedViews'] for r in complete)
    subs = sum(r['metrics']['subscribersGained'] for r in complete)
    return {'selected': len(rows), 'available': len(complete), 'engaged_views': engaged,
            'median_views': statistics.median(r['metrics']['views'] for r in complete) if complete else None,
            'median_engaged_views': statistics.median(r['metrics']['engagedViews'] for r in complete) if complete else None,
            'median_average_view_seconds': statistics.median(r['metrics']['averageViewDuration'] for r in complete) if complete else None,
            'subscribers_gained': subs, 'subscribers_per_1000_engaged': round(subs / engaged * 1000, 2) if engaged else None}


def build_report(*, history=None, analytics=None, now=None, previous=None):
    now = now or datetime.now(timezone.utc)
    if analytics is None:
        from googleapiclient.discovery import build
        analytics = build('youtubeAnalytics', 'v2', credentials=youtube_credentials(), cache_discovery=False)
    history = fetch_upload_history(days=90, now=now) if history is None else history
    today = now.astimezone(PACIFIC).date()
    # Use the supported Shorts filter, not a duration heuristic. Legacy videos
    # with no Analytics activity cannot be classified and are counted separately.
    short_ids, position = set(), 1
    while True:
        response = analytics.reports().query(
            ids='channel==MINE', startDate=str(today - timedelta(days=90)),
            endDate=str(today - timedelta(days=1)), dimensions='video',
            filters='creatorContentType==shorts', metrics='views', sort='-views',
            maxResults=200, startIndex=position).execute()
        rows = response.get('rows', [])
        short_ids.update(row[0] for row in rows)
        if len(rows) < 200:
            break
        position += 200
    public = [r for r in history if r['privacy'] == 'public']
    experimental = sorted([r for r in public if r['machine'].get('exp') == EXPERIMENT_ID
                           and r['machine'].get('fmt') == 'shorts'], key=lambda r: r['published_at'])[:10]
    before = [r for r in public if parse_time(r['published_at']) < parse_time(STARTED_AT)]
    baseline = sorted([r for r in before if r['video_id'] in short_ids or
                       r['machine'].get('fmt') == 'shorts'], key=lambda r: r['published_at'], reverse=True)[:10]
    # Freeze cohort membership across report refreshes. A deleted/private video
    # remains in the cohort as missing, rather than being replaced by a winner.
    if previous and previous.get('experiment_id') == EXPERIMENT_ID:
        lookup = {r['video_id']: r for r in public}
        for name, selected in [('baseline', baseline), ('experiment', experimental)]:
            recorded = [r for r in previous.get('videos', []) if r['cohort'] == name]
            if not recorded:
                continue
            frozen = [lookup.get(r['video_id'], {**r, 'missing': True}) for r in recorded]
            known = {r['video_id'] for r in frozen}
            if name == 'experiment':
                frozen += [r for r in selected if r['video_id'] not in known]
            if name == 'baseline':
                baseline = frozen[:10]
            else:
                experimental = frozen[:10]
    output = []
    for cohort, videos in [('baseline', baseline), ('experiment', experimental)]:
        for video in videos:
            start, end = measurement_window(video['published_at'])
            row = {'cohort': cohort, 'video_id': video['video_id'], 'title': video['title'],
                   'published_at': video['published_at'], 'window_start': str(start),
                   'window_end': str(end), 'status': 'pending', 'metrics': None}
            # Two complete additional dates for reporting lag; never pad unavailable
            # metrics with zero. Available rows still remain provisional (API revisions).
            if video.get('missing'):
                row['status'] = 'unavailable_video'
            elif today > end + timedelta(days=2):
                result = analytics.reports().query(
                    ids='channel==MINE', startDate=str(start), endDate=str(end),
                    filters=f"video=={video['video_id']};creatorContentType==shorts",
                    metrics=METRICS).execute()
                if result.get('rows'):
                    row['metrics'] = dict(zip([c['name'] for c in result['columnHeaders']], result['rows'][0]))
                    row['status'] = 'available'
                else:
                    row['status'] = 'no_analytics_rows'
            output.append(row)
    cohorts = {name: summarize([r for r in output if r['cohort'] == name]) for name in ('baseline', 'experiment')}
    sufficient = all(c['available'] >= 10 and c['engaged_views'] >= 200 for c in cohorts.values())
    result = {'experiment_id': EXPERIMENT_ID, 'started_at': STARTED_AT, 'generated_at': now.isoformat(),
              'window_definition': 'First three complete Pacific calendar days after publication; not exact first 72 hours.',
              'metric_status': 'Provisional API values; missing rows are unknown, never zero. No swipe-rate or CTR inference.',
              'baseline_selection': 'Latest ten pre-experiment public Shorts identified by upload tags or Analytics activity; zero-activity untagged videos cannot be classified.',
              'unclassified_legacy_videos': sum(r['video_id'] not in short_ids and not r['machine'].get('fmt') for r in before),
              'status': 'ready_for_comparison' if sufficient else 'collecting_insufficient_sample',
              'cohorts': cohorts, 'videos': output}
    return result


def markdown(report):
    lines = ['# Kanal büyüme deneyi', '', f"Deney: `{report['experiment_id']}` · Güncelleme: {report['generated_at']}", '',
             'İlk 10 yeni Shorts izleniyor. Ölçüm: yayın gününü hariç tutan ilk üç tam Pasifik takvim günü; tam ilk 72 saat değildir. Sonrasında veri gecikmesi için iki tam gün daha beklenir.', '',
             'Durum: ' + ('Karşılaştırma için örneklem oluştu.' if report['status'] == 'ready_for_comparison' else 'Örneklem toplanıyor; başarı/başarısızlık sonucu çıkarılmadı.'), '',
             '| Grup | Seçilen / veri gelen | Medyan izlenme | Medyan engaged | Kazanılan abone |',
             '|---|---:|---:|---:|---:|']
    for name, label in [('baseline', 'Önceki Shorts'), ('experiment', 'Yeni deney')]:
        c = report['cohorts'][name]
        lines.append(f"| {label} | {c['selected']} / {c['available']} | {c['median_views'] if c['median_views'] is not None else '—'} | {c['median_engaged_views'] if c['median_engaged_views'] is not None else '—'} | {c['subscribers_gained'] if c['available'] else '—'} |")
    lines += ['', 'Her grubun 10 videosunda veri ve en az 200 toplam engaged izlenme olmadan karşılaştırma hazır sayılmaz. Bu eşik istatistiksel anlamlılık kanıtı değildir.', '',
              'Eski Shorts sınıflaması Analytics veya format etiketine dayanır; etiketsiz ve hiç etkinliği olmayan videolar sınıflanamayıp dışarıda kalabilir. API değerleri sonradan değişebilir. Eksik veriler sıfır sayılmaz. İzlemeyi seçme/kaydırma oranı ve CTR bu raporda yoktur.', '',
              '| Video | Grup | Ölçüm tarihleri (Pasifik) | Durum |', '|---|---|---|---|']
    for r in report['videos']:
        title = r['title'].replace('|', '/').replace('\n', ' ')
        lines.append(f"| [{title}](https://youtu.be/{r['video_id']}) | {r['cohort']} | {r['window_start']} – {r['window_end']} | {r['status']} |")
    lines += ['', 'Kaynak: yetkili YouTube Data/Analytics API. [Takvim günü tanımı](https://developers.google.com/youtube/analytics/dimensions).', '']
    return '\n'.join(lines)


def main():
    target = Path('reports')
    previous_file = target / 'growth-experiment.json'
    previous = json.loads(previous_file.read_text()) if previous_file.exists() else None
    report = build_report(previous=previous)
    target.mkdir(exist_ok=True)
    # Write only after all queries succeed, so an outage preserves the old report.
    (target / 'growth-experiment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (target / 'growth-experiment.md').write_text(markdown(report))
    print(json.dumps({'status': report['status'], 'cohorts': report['cohorts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
