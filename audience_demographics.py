"""Channel age breakdown for local Analytics reports."""

from datetime import timedelta

AGE_GROUPS = ('age13-17', 'age18-24', 'age25-34', 'age35-44',
              'age45-54', 'age55-64', 'age65-')
AGE_LABELS = ('13–17', '18–24', '25–34', '35–44', '45–54', '55–64', '65+')


def fetch_age_demographics(analytics, today):
    """Last 28 and 90 complete Pacific days, allowing two days of API lag.

    A missing age bucket is unknown/suppressed, never a measured zero.
    Percentages describe the logged-in viewers available to YouTube Analytics.
    """
    end = today - timedelta(days=2)
    periods = {}
    for days in (28, 90):
        start = end - timedelta(days=days - 1)
        response = analytics.reports().query(
            ids='channel==MINE', startDate=str(start), endDate=str(end),
            metrics='viewerPercentage', dimensions='ageGroup', sort='ageGroup',
        ).execute()
        headers = [item['name'] for item in response.get('columnHeaders', [])]
        values = {}
        if 'ageGroup' in headers and 'viewerPercentage' in headers:
            for row in response.get('rows', []):
                item = dict(zip(headers, row))
                values[item['ageGroup']] = item['viewerPercentage']
        periods[str(days)] = {
            'start_date': str(start), 'end_date': str(end),
            'viewer_percentages': {age: values.get(age) for age in AGE_GROUPS},
        }
    return {'retrieved_on': str(today), 'periods': periods,
            'note': 'Missing age groups were not reported by YouTube; they are not zero. '
                    'Age data covers the logged-in viewers represented in Analytics.'}


def age_markdown_lines(demographics):
    periods = demographics['periods']
    lines = ['## İzleyici yaş dağılımı', '',
             f"Son 28 gün: {periods['28']['start_date']} – {periods['28']['end_date']}; "
             f"son 90 gün: {periods['90']['start_date']} – {periods['90']['end_date']} "
             f"(Pasifik takvimi; sorgu {demographics['retrieved_on']}).", '',
             '| Yaş | Son 28 gün | Son 90 gün |', '|---|---:|---:|']
    for age, label in zip(AGE_GROUPS, AGE_LABELS):
        values = [periods[days]['viewer_percentages'][age] for days in ('28', '90')]
        cells = [f'%{value:g}' if value is not None else 'Raporlanmadı' for value in values]
        lines.append(f'| {label} | {cells[0]} | {cells[1]} |')
    lines += ['', 'Yüzdeler YouTube Analytics’in raporladığı oturum açmış izleyicilere dayanır. '
              '“Raporlanmadı” sıfır izleyici anlamına gelmez; düşük veri veya gizlilik sınırları nedeniyle yaş grubu gösterilmeyebilir.']
    return lines
