import * as echarts from 'echarts';
const coldData = [[0.43,11.75],[0.66,10.46],[1.05,10.31],[300.09,1.60]];
const aiData = [[0.29,19.09],[0.38,11.75],[41.59,0.92]];
const option = {
  xAxis: { type: 'value', min: 0, max: 310 },
  yAxis: { type: 'value', min: 0, max: 22 },
  series: [
    { name: 'cold', type: 'line', data: coldData },
    { name: 'ai', type: 'line', data: aiData, markLine: { silent:true, symbol:'none', data:[{yAxis:1}] } },
  ],
};
try {
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 600, height: 360 });
  chart.setOption(option);
  const svg = chart.renderToSVGString();
  console.log('SVG length:', svg.length, '| has path:', svg.includes('<path'), '| OPTION VALID');
} catch (e) {
  console.log('ERROR:', e.message);
}
