// Mock API 服务层 - 模拟异步 API 调用

import {
  Location,
  RoutePlanRequest,
  RoutePlanResponse,
} from './types'
import {
  MOCK_LOCATIONS,
  mockRoutePlan,
  searchLocations,
} from './mockData'

// 模拟网络延迟
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// Mock API: 搜索地点
export async function mockSearchLocations(query: string): Promise<Location[]> {
  await delay(300) // 模拟 300ms 网络延迟
  return searchLocations(query)
}

// Mock API: 获取所有地点（用于地图标记）
export async function mockGetAllLocations(): Promise<Location[]> {
  await delay(200)
  return MOCK_LOCATIONS
}

// Mock API: 路径规划
export async function mockPlanRoute(
  request: RoutePlanRequest
): Promise<RoutePlanResponse> {
  await delay(500) // 模拟 500ms 路径计算延迟
  
  return mockRoutePlan(
    request.origin,
    request.destination,
    request.mode,
    request.time,
    request.preference
  )
}

// Mock API: 根据 ID 获取地点详情
export async function mockGetLocationById(id: string): Promise<Location | null> {
  await delay(150)
  return MOCK_LOCATIONS.find((loc) => loc.id === id) || null
}

// 示例：如何在组件中使用
// 
// import { mockSearchLocations, mockPlanRoute } from '@/lib/mockApi'
// 
// // 搜索地点
// const locations = await mockSearchLocations('Central Park')
// 
// // 规划路径
// const result = await mockPlanRoute({
//   origin: locations[0],
//   destination: locations[1],
//   mode: 'walking',
//   time: new Date().toISOString(),
//   preference: 'sun'
// })
// 
// console.log(result.routes) // 3条路线
// console.log(result.lightIntensity) // 当前光线强度
