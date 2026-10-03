"""Read-only rolling weekly channel report, independent of the experiment cohort."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from publication_history import youtube_credentials

METRICS = 'views,engagedViews,estimatedMinutesWatched,subscribersGained,subscribersLost'


def query_rows(api, start, end, **kwargs):
    response = api.reports().query(ids='channel==MINE', startDate=str(start),
                                   endDate=str(end), metrics=METRICS, **kwargs).execute()
    names = [c['name'] for c in response.get('columnHeaders', [])]
    return [dict(zip(names, row)) for row in response.get('rows', [])]


def build_status(api, now=None):
    now = now or datetime.now(timezone.utc)
    yesterday = now.astimezone(ZoneInfo('America/Los_Angeles')).date() - timedelta(days=1)
    daily = query_rows(api, yesterday - timedelta(days=27), yesterday, dimensions='day')
    if not daily:
        raise RuntimeError('No daily Analytics data; preserving the previous channel report')
    latest = max(datetime.fromisoformat(r['day']).date() for r in daily)
    periods = {}
    for name, end in [('current', latest), ('previous', latest - timedelta(days=7))]:
        start = end - timedelta(days=6)
        observed = [r for r in daily if str(start) <= r['day'] <= str(end)]
        missing = sorted({str(start + timedelta(days=i)) for i in range(7)} - {r['day'] for r in observed})
        totals = {metric: sum(r[metric] for r in observed) for metric in METRICS.split(',')}
        totals['netSubscribers'] = totals['subscribersGained'] - totals['subscribersLost']
        format_rows = query_rows(api, start, end, dimensions='creatorContentType')
        lookup = {r['creatorContentType'].lower().replace('_', ''): r for r in format_rows}
        formats = {kind: lookup.get(kind) for kind in ('shorts', 'videoondemand')}
        formats['unspecified'] = lookup.get('creatorcontenttypeunspecified') or lookup.get('unspecified')
        periods[name] = dict(start=str(start), end=str(end), missing_dates=missing,
                             totals=totals, formats=formats)
    return dict(generated_at=now.isoformat(), latest_analytics_date=str(latest),
                requested_through=str(yesterday), periods=periods)


def markdown(report):
    current, previous = [report['periods'][key] for key in ('current', 'previous')]
    lines = ['# Haftalık kanal durumu', '', f"Güncelleme: {report['generated_at']}", '',
             f"Son Analytics günü: **{report['latest_analytics_date']}**. Tarihler Pasifik saat dilimindedir.",
             'API gecikmesi nedeniyle dönemler veri gelen son tarihe göre kaydırılır. Eksik günler sıfır sayılmaz.', '',
             '| Ölçüm | Önceki dönem | Son dönem | Değişim |', '|---|---:|---:|---:|']
    for metric, label in [('views', 'İzlenme'), ('engagedViews', 'Engaged izlenme'),
                          ('estimatedMinutesWatched', 'İzlenme süresi (dakika)'),
                          ('netSubscribers', 'Net abone')]:
        old, new = previous['totals'][metric], current['totals'][metric]
        change = f'{(new / old - 1) * 100:+.1f}%' if old and not any(p['missing_dates'] for p in (previous,current)) else '—'
        lines.append(f'| {label} | {old} | {new} | {change} |')
    lines += ['', f"Önceki dönem: {previous['start']} – {previous['end']}; son dönem: {current['start']} – {current['end']}.", '',
              '| Dönem / format | İzlenme | Engaged | Dakika | Kazanılan / kaybedilen abone |',
              '|---|---:|---:|---:|---:|']
    for name, period in [('Önceki', previous), ('Son', current)]:
        for fmt, label in [('shorts', 'Shorts'), ('videoondemand', 'Uzun video'), ('unspecified', 'Formatı belirsiz')]:
            row = period['formats'][fmt]
            if row:
                lines.append(f"| {name} / {label} | {row['views']} | {row['engagedViews']} | {row['estimatedMinutesWatched']} | {row['subscribersGained']} / {row['subscribersLost']} |")
            else:
                lines.append(f'| {name} / {label} | — | — | — | — |')
    for name, period in [('Önceki', previous), ('Son', current)]:
        if period['missing_dates']:
            lines += ['', f"Eksik günler ({name}): {', '.join(period['missing_dates'])}. Dönem toplamı eksik olabilir."]
    lines += ['', 'Format toplamları ile günlük toplamlar API revizyonları ve yuvarlama nedeniyle küçük farklar gösterebilir. Bu dönemler kanalın tüm videolarındaki etkinliği kapsar; eşit yaşlı video deneyi değildir. Engaged izlenme, tekil izleyici veya izlemeyi seçme/kaydırma oranı değildir.', '']
    return '\n'.join(lines)


def main():
    from googleapiclient.discovery import build
    report = build_status(build('youtubeAnalytics', 'v2', credentials=youtube_credentials(), cache_discovery=False))
    target = Path('reports'); target.mkdir(exist_ok=True)
    (target / 'channel-status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (target / 'channel-status.md').write_text(markdown(report))
    print(json.dumps({'latest_analytics_date': report['latest_analytics_date']}))


if __name__ == '__main__':
    main()
