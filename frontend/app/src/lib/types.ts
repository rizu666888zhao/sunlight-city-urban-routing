// 地点数据类型
export interface Location {
  id: string
  name: string
  lat: number
  lng: number
  address?: string
}

// 路径点类型
export interface RoutePoint {
  lat: number
  lng: number
}

// 单条路线类型
export interface Route {
  id: string
  points: RoutePoint[]
  distance: number // 距离（公里）
  sunExposure: number // 光照量 0-100%
  duration: number // 预计时长（分钟）
  color: string // 路线显示颜色
}

// 路径规划请求参数
export interface RoutePlanRequest {
  origin: Location
  destination: Location
  mode: 'walking' | 'cycling' // 步行或骑行
  time: string // ISO 时间格式
  preference: 'sun' | 'shade' // 趋光或趋阴
}

// 路径规划响应
export interface RoutePlanResponse {
  routes: Route[]
  lightIntensity: number // 当前光线强度 0-100
  isLowLight: boolean // 是否低光照（触发最短路径）
}
