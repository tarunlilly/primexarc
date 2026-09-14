
import { Link } from 'react-router-dom'

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="bg-[#A00D24] text-white">
      <div className="container mx-auto px-4 py-8">
        <div className="border-t border-white/20 pt-8 mt-8">
          <div className="flex flex-col md:flex-row justify-between items-center space-y-4 md:space-y-0">
            <div className="text-white/80 text-sm">
              © {currentYear} PrimeData. All rights reserved.
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}
