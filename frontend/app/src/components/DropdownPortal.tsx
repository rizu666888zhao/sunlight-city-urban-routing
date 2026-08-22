'use client'

import React, { useEffect, useState, MutableRefObject } from 'react'
import ReactDOM from 'react-dom'

interface DropdownPortalProps {
  anchorRef: MutableRefObject<HTMLElement | null>
  children: React.ReactNode
}

export default function DropdownPortal({ anchorRef, children }: DropdownPortalProps) {
  const [container] = useState(() => document.createElement('div'))
  const [style, setStyle] = useState<React.CSSProperties>({ position: 'absolute', top: 0, left: 0 })

  useEffect(() => {
    container.style.position = 'absolute'
    container.style.zIndex = '9999'
    document.body.appendChild(container)
    return () => {
      if (document.body.contains(container)) document.body.removeChild(container)
    }
  }, [container])

  useEffect(() => {
    function updatePosition() {
      const anchor = anchorRef?.current
      if (!anchor) return
      const rect = anchor.getBoundingClientRect()
      const top = rect.bottom + window.scrollY + 8 // small offset
      const left = rect.right + window.scrollX - 200 // align right edge, fallback width

      setStyle({ position: 'absolute', top: `${top}px`, left: `${left}px`, minWidth: '180px' })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    const obs = new MutationObserver(updatePosition)
    obs.observe(document.body, { attributes: true, childList: true, subtree: true })

    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
      obs.disconnect()
    }
  }, [anchorRef, container])

  return ReactDOM.createPortal(
    <div style={style}>
      {children}
    </div>,
    container,
  )
}
