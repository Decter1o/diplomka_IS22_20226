export default function AlertsPagination({ currentPage, totalPages, onPageChange }) {
  const getPageNumbers = () => {
    const delta = 2
    const range = []
    const left = currentPage - delta
    const right = currentPage + delta + 1

    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= left && i < right)) {
        range.push(i)
      } else if (range[range.length - 1] !== '...') {
        range.push('...')
      }
    }

    return range
  }

  const pages = getPageNumbers()

  return (
    <nav aria-label="Пагинация">
      <ul className="pagination justify-content-center">
        {/* Предыдущая */}
        <li className={`page-item${currentPage === 1 ? ' disabled' : ''}`}>
          <button
            className="page-link"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
          >
            <i className="bi bi-chevron-left me-1"></i>
            Предыдущая
          </button>
        </li>

        {/* Номера страниц */}
        {pages.map((page, idx) => (
          page === '...' ? (
            <li key={`dots-${idx}`} className="page-item disabled">
              <span className="page-link">…</span>
            </li>
          ) : (
            <li key={page} className={`page-item${page === currentPage ? ' active' : ''}`}>
              <button
                className="page-link"
                onClick={() => onPageChange(page)}
              >
                {page}
              </button>
            </li>
          )
        ))}

        {/* Следующая */}
        <li className={`page-item${currentPage === totalPages ? ' disabled' : ''}`}>
          <button
            className="page-link"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
          >
            Следующая
            <i className="bi bi-chevron-right ms-1"></i>
          </button>
        </li>
      </ul>
    </nav>
  )
}
