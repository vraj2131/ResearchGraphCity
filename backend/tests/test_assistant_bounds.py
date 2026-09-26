from app.assistant import build_evidence_packet


def test_many_memberships_keep_prompts_bounded_and_preserve_primary_context():
    locations = [dict(building_id=f'B{i}', floor_id='F1', floors=[
        dict(floor_id=f'F{j}', floor_index=j, summary={'large': 'x' * 1000}) for j in range(100)
    ]) for i in range(100)]
    paper = dict(paper_id='P1', evidence_id='paper:W1', building_id='B99', locations=locations)
    class Repository:
        def search_papers(self, *args, **kwargs):
            return [paper]
        def relationships_for_buildings(self, *args, **kwargs):
            return []
        def get_timeline(self, *args, **kwargs):
            return {'years': []}
    packet = build_evidence_packet(Repository(), 'city', 'graph')
    result = packet['papers'][0]
    assert len(result['locations']) <= 16
    assert result['locations'][0]['building_id'] == 'B99'
    assert result['location_count'] == 100
    assert result['locations_truncated'] is True
    assert all('floors' not in location for location in result['locations'])
    assert len(paper['locations']) == 100  # A prompt projection cannot truncate API data.
