import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorPanel from '../../src/components/ErrorPanel.vue'

describe('ErrorPanel', () => {
  it('emits goto when line button clicked', async () => {
    const wrapper = mount(ErrorPanel, {
      props: {
        issues: [
          {
            id: '1',
            level: 'warning',
            line: 12,
            message: 'demo',
          },
        ],
      },
    })

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('goto')?.[0]).toEqual([12])
  })
})
