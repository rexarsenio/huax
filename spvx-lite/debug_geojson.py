#!/usr/bin/env python3
"""Debug GeoJSON parsing errors."""

import json
from pathlib import Path

def check_geojson(filepath):
    """Check if a GeoJSON file is valid."""
    p = Path(filepath)

    if not p.exists():
        print(f'❌ {filepath} does not exist')
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            data = json.loads(content)

        features = data.get('features', [])
        print(f'✅ {filepath} is valid JSON')
        print(f'   Type: {data.get("type")}')
        print(f'   Features: {len(features)}')

        # Show feature IDs if available
        if features:
            ids = [f.get('properties', {}).get('id', 'NO_ID') for f in features[:5]]
            print(f'   First 5 IDs: {", ".join(ids)}')

        return True

    except json.JSONDecodeError as e:
        print(f'❌ {filepath} has JSON syntax error!')
        print(f'   Error: {e.msg}')
        print(f'   Line {e.lineno}, Column {e.colno}')
        print(f'   Position: {e.pos}')

        # Show context around error
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        start = max(0, e.lineno - 5)
        end = min(len(lines), e.lineno + 3)

        print(f'\n   Context (lines {start+1} to {end}):')
        print('   ' + '-' * 70)
        for i in range(start, end):
            marker = '>>> ' if i == e.lineno - 1 else '    '
            line_num = f'{i+1:4d}'
            line_content = lines[i].rstrip()
            print(f'{marker}{line_num}: {line_content}')

            # Show error position marker
            if i == e.lineno - 1:
                # Calculate column position accounting for line number prefix
                prefix_len = len(marker) + len(line_num) + 2
                spaces = ' ' * (prefix_len + e.colno - 1)
                print(f'{spaces}^ ERROR HERE')

        print('   ' + '-' * 70)

        # Common fixes
        print('\n   💡 Common fixes:')
        print('   - Missing comma between objects/arrays')
        print('   - Trailing comma before closing } or ]')
        print('   - Unescaped quotes inside strings')
        print('   - Missing closing brace or bracket')

        return False

    except Exception as e:
        print(f'❌ {filepath} error: {e}')
        return False

if __name__ == '__main__':
    print('🔍 Checking GeoJSON files...\n')

    files = [
        'data/geo/polygons.geojson',
        'data/geo/gates.geojson',
    ]

    all_valid = True
    for filepath in files:
        result = check_geojson(filepath)
        all_valid = all_valid and result
        print()

    if all_valid:
        print('✅ All GeoJSON files are valid!')
        exit(0)
    else:
        print('❌ Some GeoJSON files have errors. Fix them and try again.')
        exit(1)
