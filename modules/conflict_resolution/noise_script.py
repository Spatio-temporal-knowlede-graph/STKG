#!/usr/bin/env python3
"""
Conflict resolution module에서는 다음과 같은 노이즈를 정의한다.

- state conflict: 서로 다른 소스에서 동시간대의 동일 객체에 대해 서로 양립할 수 없는 상태 또는 속성값을 기록한 경우
- event conflict: 서로 다른 소스에서 동일 이벤트(or 사실)에 대해 서로 다른 발생 시각을 기록한 경우
- spatial conflict: 서로 다른 소스에서 동시간대의 동일 객체가 서로 양립할 수 없는 지역 또는 공간 영역에 존재하는 경우 
  
"""