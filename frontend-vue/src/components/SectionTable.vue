<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th v-for="head in headers" :key="head">{{ head }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, idx) in rows" :key="row.key || idx">
          <td v-for="head in headers" :key="head">{{ row[head] ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  headers: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
})
</script>
