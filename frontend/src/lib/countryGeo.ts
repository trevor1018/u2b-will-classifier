// Static country → (lat, lon, zoom) dictionary used to fly the map to a
// country's *geographic* centre when the user picks it from the filter,
// instead of fitting bounds to the case data points (which can be misleading
// for cross-border cases or sparse data).
//
// Zoom levels chosen so the country fills the viewport without too much
// surrounding land:
//   tiny city-state    zoom 8   (Singapore, HK)
//   small country      zoom 6-7 (Switzerland, Belgium, Netherlands, NZ)
//   medium country     zoom 5   (Japan, UK, Italy, Korea, Germany, France)
//   large country      zoom 4   (USA, China, Australia, Brazil, Argentina)
//   continental giant  zoom 3   (Russia, Canada)

export interface CountryGeo {
  lat: number;
  lon: number;
  zoom: number;
}

export const COUNTRY_GEO: Record<string, CountryGeo> = {
  // 東亞
  日本: { lat: 36.2048, lon: 138.2529, zoom: 5 },
  韓國: { lat: 35.9078, lon: 127.7669, zoom: 6 },
  中國: { lat: 35.8617, lon: 104.1954, zoom: 4 },
  台灣: { lat: 23.6978, lon: 120.9605, zoom: 7 },
  香港: { lat: 22.3193, lon: 114.1694, zoom: 9 },
  澳門: { lat: 22.1987, lon: 113.5439, zoom: 11 },
  蒙古: { lat: 46.8625, lon: 103.8467, zoom: 4 },
  北韓: { lat: 40.3399, lon: 127.5101, zoom: 6 },

  // 東南亞
  泰國: { lat: 15.87, lon: 100.9925, zoom: 5 },
  越南: { lat: 14.0583, lon: 108.2772, zoom: 5 },
  馬來西亞: { lat: 4.2105, lon: 101.9758, zoom: 6 },
  新加坡: { lat: 1.3521, lon: 103.8198, zoom: 11 },
  印尼: { lat: -2.5489, lon: 118.0149, zoom: 4 },
  菲律賓: { lat: 12.8797, lon: 121.774, zoom: 5 },
  緬甸: { lat: 21.9162, lon: 95.956, zoom: 5 },
  柬埔寨: { lat: 12.5657, lon: 104.991, zoom: 6 },
  寮國: { lat: 19.8563, lon: 102.4955, zoom: 6 },

  // 南亞
  印度: { lat: 20.5937, lon: 78.9629, zoom: 4 },
  巴基斯坦: { lat: 30.3753, lon: 69.3451, zoom: 5 },
  孟加拉: { lat: 23.685, lon: 90.3563, zoom: 7 },
  尼泊爾: { lat: 28.3949, lon: 84.124, zoom: 7 },
  斯里蘭卡: { lat: 7.8731, lon: 80.7718, zoom: 7 },

  // 西亞 / 中東
  土耳其: { lat: 38.9637, lon: 35.2433, zoom: 5 },
  以色列: { lat: 31.0461, lon: 34.8516, zoom: 7 },
  伊朗: { lat: 32.4279, lon: 53.688, zoom: 5 },
  伊拉克: { lat: 33.2232, lon: 43.6793, zoom: 6 },
  沙烏地阿拉伯: { lat: 23.8859, lon: 45.0792, zoom: 5 },
  阿聯: { lat: 23.4241, lon: 53.8478, zoom: 6 },

  // 北美
  美國: { lat: 39.8283, lon: -98.5795, zoom: 4 },
  加拿大: { lat: 56.1304, lon: -106.3468, zoom: 3 },
  墨西哥: { lat: 23.6345, lon: -102.5528, zoom: 5 },
  古巴: { lat: 21.5218, lon: -77.7812, zoom: 6 },
  巴拿馬: { lat: 8.538, lon: -80.7821, zoom: 7 },
  阿魯巴: { lat: 12.5211, lon: -69.9683, zoom: 11 },
  特立尼達和多巴哥: { lat: 10.6918, lon: -61.2225, zoom: 9 },

  // 中南美
  巴西: { lat: -14.235, lon: -51.9253, zoom: 4 },
  阿根廷: { lat: -38.4161, lon: -63.6167, zoom: 4 },
  智利: { lat: -35.6751, lon: -71.543, zoom: 4 },
  秘魯: { lat: -9.19, lon: -75.0152, zoom: 5 },
  哥倫比亞: { lat: 4.5709, lon: -74.2973, zoom: 5 },
  委內瑞拉: { lat: 6.4238, lon: -66.5897, zoom: 5 },

  // 西歐
  英國: { lat: 55.3781, lon: -3.436, zoom: 5 },
  愛爾蘭: { lat: 53.4129, lon: -8.2439, zoom: 7 },
  法國: { lat: 46.2276, lon: 2.2137, zoom: 5 },
  德國: { lat: 51.1657, lon: 10.4515, zoom: 5 },
  義大利: { lat: 41.8719, lon: 12.5674, zoom: 5 },
  西班牙: { lat: 40.4637, lon: -3.7492, zoom: 5 },
  葡萄牙: { lat: 39.3999, lon: -8.2245, zoom: 6 },
  荷蘭: { lat: 52.1326, lon: 5.2913, zoom: 7 },
  比利時: { lat: 50.5039, lon: 4.4699, zoom: 7 },
  瑞士: { lat: 46.8182, lon: 8.2275, zoom: 7 },
  奧地利: { lat: 47.5162, lon: 14.5501, zoom: 6 },
  盧森堡: { lat: 49.8153, lon: 6.1296, zoom: 9 },

  // 北歐
  瑞典: { lat: 60.1282, lon: 18.6435, zoom: 4 },
  挪威: { lat: 60.472, lon: 8.4689, zoom: 4 },
  丹麥: { lat: 56.2639, lon: 9.5018, zoom: 6 },
  芬蘭: { lat: 61.9241, lon: 25.7482, zoom: 4 },
  冰島: { lat: 64.9631, lon: -19.0208, zoom: 6 },

  // 中東歐
  波蘭: { lat: 51.9194, lon: 19.1451, zoom: 5 },
  捷克: { lat: 49.8175, lon: 15.473, zoom: 6 },
  匈牙利: { lat: 47.1625, lon: 19.5033, zoom: 6 },
  羅馬尼亞: { lat: 45.9432, lon: 24.9668, zoom: 6 },
  保加利亞: { lat: 42.7339, lon: 25.4858, zoom: 6 },
  希臘: { lat: 39.0742, lon: 21.8243, zoom: 6 },

  // 東歐 / 蘇聯
  俄羅斯: { lat: 61.524, lon: 105.3188, zoom: 3 },
  蘇聯: { lat: 61.524, lon: 105.3188, zoom: 3 },
  烏克蘭: { lat: 48.3794, lon: 31.1656, zoom: 5 },
  白俄羅斯: { lat: 53.7098, lon: 27.9534, zoom: 6 },
  塞爾維亞: { lat: 44.0165, lon: 21.0059, zoom: 6 },

  // 大洋洲
  澳洲: { lat: -25.2744, lon: 133.7751, zoom: 4 },
  紐西蘭: { lat: -40.9006, lon: 174.886, zoom: 5 },

  // 非洲
  南非: { lat: -30.5595, lon: 22.9375, zoom: 5 },
  肯亞: { lat: -0.0236, lon: 37.9062, zoom: 5 },
  奈及利亞: { lat: 9.082, lon: 8.6753, zoom: 6 },
  埃及: { lat: 26.0975, lon: 31.2357, zoom: 5 },
  摩洛哥: { lat: 31.7917, lon: -7.0926, zoom: 5 },
};
