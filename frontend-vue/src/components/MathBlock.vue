<template>
  <span ref="el" v-html="rendered"></span>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps({
  expr: { type: String, required: true },
  display: { type: Boolean, default: true },
})

const el = ref(null)
const rendered = ref('')

function render() {
  try {
    rendered.value = katex.renderToString(props.expr, {
      displayMode: props.display,
      throwOnError: false,
    })
  } catch (e) {
    rendered.value = `<code>${props.expr}</code>`
  }
}

onMounted(render)
watch(() => props.expr, render)
</script>
