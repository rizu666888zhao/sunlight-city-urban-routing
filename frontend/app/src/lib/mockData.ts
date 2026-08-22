import { Location, Route, RoutePlanResponse } from './types'

// Mock 地点数据（New York 区域）
export const MOCK_LOCATIONS: Location[] = [
  { id: '1', name: 'Central Park', lat: 40.785, lng: -73.968, address: 'Central Park, New York, NY' },
  { id: '2', name: 'Times Square', lat: 40.758, lng: -73.985, address: 'Times Square, New York, NY' },
  { id: '3', name: 'Empire State Building', lat: 40.748, lng: -73.985, address: '350 5th Ave, New York, NY' },
  { id: '4', name: 'Grand Central Terminal', lat: 40.753, lng: -73.977, address: '89 E 42nd St, New York, NY' },
  { id: '5', name: 'Bryant Park', lat: 40.754, lng: -73.983, address: 'Bryant Park, New York, NY' },
  { id: '6', name: 'Madison Square Garden', lat: 40.750, lng: -73.993, address: '4 Pennsylvania Plaza, New York, NY' },
  { id: '7', name: 'Washington Square Park', lat: 40.731, lng: -73.997, address: 'Washington Square Park, New York, NY' },
  { id: '8', name: 'Columbia University', lat: 40.808, lng: -73.962, address: 'Columbia University, New York, NY' },
]

// Mock 路径数据生成函数
export function generateMockRoutes(
  origin: Location,
  destination: Location,
  mode: 'walking' | 'cycling',
  preference: 'sun' | 'shade'
): Route[] {
  const baseDistance = calculateDistance(origin, destination)
  const baseSpeed = mode === 'walking' ? 5 : 15 // km/h
  
  // 生成3条不同的路线
  const routes: Route[] = [
    {
      id: 'route-1',
      points: generateRoutePoints(origin, destination, 'direct'),
      distance: baseDistance,
      sunExposure: preference === 'sun' ? 85 : 35,
      duration: Math.round((baseDistance / baseSpeed) * 60),
      color: preference === 'sun' ? '#3B82F6' : '#EF4444', // 蓝色（冷）或红色（热）
    },
    {
      id: 'route-2',
      points: generateRoutePoints(origin, destination, 'scenic'),
      distance: baseDistance * 1.15,
      sunExposure: preference === 'sun' ? 65 : 55,
      duration: Math.round((baseDistance * 1.15 / baseSpeed) * 60),
      color: '#F59E0B', // 黄色（中等）
    },
    {
      id: 'route-3',
      points: generateRoutePoints(origin, destination, 'alternative'),
      distance: baseDistance * 1.25,
      sunExposure: preference === 'sun' ? 45 : 75,
      duration: Math.round((baseDistance * 1.25 / baseSpeed) * 60),
      color: preference === 'sun' ? '#EF4444' : '#3B82F6',
    },
  ]

  // 根据偏好排序（趋光则光照高的在前，趋阴则光照低的在前）
  return routes.sort((a, b) => 
    preference === 'sun' ? b.sunExposure - a.sunExposure : a.sunExposure - b.sunExposure
  )
}

// 计算两点间的直线距离（简化版，单位：公里）
function calculateDistance(from: Location, to: Location): number {
  const R = 6371 // 地球半径（公里）
  const dLat = toRad(to.lat - from.lat)
  const dLng = toRad(to.lng - from.lng)
  
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(from.lat)) * Math.cos(toRad(to.lat)) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2)
  
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return Math.round(R * c * 100) / 100 // 保留两位小数
}

function toRad(degrees: number): number {
  return degrees * Math.PI / 180
}

// 生成路径点（简化版，实际应该是真实路径）
function generateRoutePoints(
  origin: Location,
  destination: Location,
  routeType: 'direct' | 'scenic' | 'alternative'
): { lat: number; lng: number }[] {
  const points = [{ lat: origin.lat, lng: origin.lng }]
  
  // 根据路线类型生成中间点
  const numPoints = routeType === 'direct' ? 3 : routeType === 'scenic' ? 5 : 4
  
  for (let i = 1; i < numPoints; i++) {
    const ratio = i / numPoints
    
    // 添加一些随机偏移来模拟不同路线
    const offset = routeType === 'direct' ? 0 : 
                   routeType === 'scenic' ? 0.003 : 0.002
    const randomOffset = (Math.random() - 0.5) * offset
    
    points.push({
      lat: origin.lat + (destination.lat - origin.lat) * ratio + randomOffset,
      lng: origin.lng + (destination.lng - origin.lng) * ratio + randomOffset,
    })
  }
  
  points.push({ lat: destination.lat, lng: destination.lng })
  return points
}

// Mock 完整的路径规划响应
export function mockRoutePlan(
  origin: Location,
  destination: Location,
  mode: 'walking' | 'cycling',
  time: string,
  preference: 'sun' | 'shade'
): RoutePlanResponse {
  const routes = generateMockRoutes(origin, destination, mode, preference)
  
  // 模拟光线强度（根据时间）
  const hour = new Date(time).getHours()
  let lightIntensity: number
  
  if (hour >= 6 && hour < 8) lightIntensity = 40 // 清晨
  else if (hour >= 8 && hour < 10) lightIntensity = 70 // 上午
  else if (hour >= 10 && hour < 16) lightIntensity = 95 // 中午到下午
  else if (hour >= 16 && hour < 18) lightIntensity = 60 // 傍晚
  else if (hour >= 18 && hour < 20) lightIntensity = 30 // 黄昏
  else lightIntensity = 10 // 夜晚
  
  const isLowLight = lightIntensity < 30
  
  return {
    routes,
    lightIntensity,
    isLowLight,
  }
}

// 地点搜索 Mock 函数
export function searchLocations(query: string): Location[] {
  if (!query || query.trim() === '') return []
  
  const lowerQuery = query.toLowerCase()
  return MOCK_LOCATIONS.filter(
    (loc) =>
      loc.name.toLowerCase().includes(lowerQuery) ||
      loc.address?.toLowerCase().includes(lowerQuery)
  ).slice(0, 5) // 最多返回5个结果
}
