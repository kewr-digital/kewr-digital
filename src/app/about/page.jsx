import Image from 'next/image'

import { Border } from '@/components/Border'
import { ContactSection } from '@/components/ContactSection'
import { Container } from '@/components/Container'
import { FadeIn, FadeInStagger } from '@/components/FadeIn'
import { GridList, GridListItem } from '@/components/GridList'
import { PageIntro } from '@/components/PageIntro'
import { PageLinks } from '@/components/PageLinks'
import { SectionIntro } from '@/components/SectionIntro'
import { StatList, StatListItem } from '@/components/StatList'
import imageAngelaFisher from '@/images/team/angela-fisher.jpg'
import imageBenjaminRussel from '@/images/team/benjamin-russel.jpg'
import imageBlakeReid from '@/images/team/blake-reid.jpg'
import imageChelseaHagon from '@/images/team/chelsea-hagon.jpg'
import imageDriesVincent from '@/images/team/dries-vincent.jpg'
import imageEmmaDorsey from '@/images/team/emma-dorsey.jpg'
import imageJeffreyWebb from '@/images/team/jeffrey-webb.jpg'
import imageKathrynMurphy from '@/images/team/kathryn-murphy.jpg'
import imageLeonardKrasner from '@/images/team/leonard-krasner.jpg'
import imageLeslieAlexander from '@/images/team/leslie-alexander.jpg'
import imageMichaelFoster from '@/images/team/michael-foster.jpg'
import imageWhitneyFrancis from '@/images/team/whitney-francis.jpg'
import { loadArticles } from '@/lib/mdx'

function Culture() {
  return (
    <div className="mt-24 rounded-4xl bg-neutral-950 py-24 sm:mt-32 lg:mt-40 lg:py-32">
      <SectionIntro
        eyebrow="Our culture"
        title="Balance your passion with your passion for life."
        invert
      >
        <p>Our culture is built on the foundation of our core values</p>
      </SectionIntro>
      <Container className="mt-16">
        <GridList>
          <GridListItem title="Integrity" invert>
            We uphold the highest ethical standards in all our interactions,
            both internally and externally.
          </GridListItem>
          <GridListItem title="Innovation" invert>
            We embrace new ideas and technologies, fostering a culture of
            experimentation and continuous improvement.
          </GridListItem>
          <GridListItem title="Collaboration" invert>
            We believe in the power of teamwork and open communication, working
            together to achieve common goals.
          </GridListItem>
          <GridListItem title="Excellence" invert>
            We strive for perfection in everything we do, delivering exceptional
            products and services that exceed expectations.
          </GridListItem>
        </GridList>
      </Container>
    </div>
  )
}

const team = [
  {
    title: 'Leadership',
    people: [
      {
        name: 'Leslie Alexander',
        role: 'Co-Founder / CEO',
        image: { src: imageLeslieAlexander },
      },
      {
        name: 'Michael Foster',
        role: 'Co-Founder / CTO',
        image: { src: imageMichaelFoster },
      },
      {
        name: 'Dries Vincent',
        role: 'Partner & Business Relations',
        image: { src: imageDriesVincent },
      },
    ],
  },
  {
    title: 'Team',
    people: [
      {
        name: 'Chelsea Hagon',
        role: 'Senior Developer',
        image: { src: imageChelseaHagon },
      },
      {
        name: 'Emma Dorsey',
        role: 'Senior Designer',
        image: { src: imageEmmaDorsey },
      },
      {
        name: 'Leonard Krasner',
        role: 'VP, User Experience',
        image: { src: imageLeonardKrasner },
      },
      {
        name: 'Blake Reid',
        role: 'Junior Copywriter',
        image: { src: imageBlakeReid },
      },
      {
        name: 'Kathryn Murphy',
        role: 'VP, Human Resources',
        image: { src: imageKathrynMurphy },
      },
      {
        name: 'Whitney Francis',
        role: 'Content Specialist',
        image: { src: imageWhitneyFrancis },
      },
      {
        name: 'Jeffrey Webb',
        role: 'Account Coordinator',
        image: { src: imageJeffreyWebb },
      },
      {
        name: 'Benjamin Russel',
        role: 'Senior Developer',
        image: { src: imageBenjaminRussel },
      },
      {
        name: 'Angela Fisher',
        role: 'Front-end Developer',
        image: { src: imageAngelaFisher },
      },
    ],
  },
]

// function Team() {
//   return (
//     <Container className="mt-24 sm:mt-32 lg:mt-40">
//       <div className="space-y-24">
//         {team.map((group) => (
//           <FadeInStagger key={group.title}>
//             <Border as={FadeIn} />
//             <div className="grid grid-cols-1 gap-6 pt-12 sm:pt-16 lg:grid-cols-4 xl:gap-8">
//               <FadeIn>
//                 <h2 className="font-display text-2xl font-semibold text-neutral-950">
//                   {group.title}
//                 </h2>
//               </FadeIn>
//               <div className="lg:col-span-3">
//                 <ul
//                   role="list"
//                   className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:gap-8"
//                 >
//                   {group.people.map((person) => (
//                     <li key={person.name}>
//                       <FadeIn>
//                         <div className="group relative overflow-hidden rounded-3xl bg-neutral-100">
//                           <Image
//                             alt=""
//                             {...person.image}
//                             className="h-96 w-full object-cover grayscale transition duration-500 motion-safe:group-hover:scale-105"
//                           />
//                           <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black to-black/0 to-40% p-6">
//                             <p className="font-display text-base/6 font-semibold tracking-wide text-white">
//                               {person.name}
//                             </p>
//                             <p className="mt-2 text-sm text-white">
//                               {person.role}
//                             </p>
//                           </div>
//                         </div>
//                       </FadeIn>
//                     </li>
//                   ))}
//                 </ul>
//               </div>
//             </div>
//           </FadeInStagger>
//         ))}
//       </div>
//     </Container>
//   )
// }

export const metadata = {
  title: 'About Us',
  description:
    'We believe that our strength lies in our collaborative approach, which puts our clients at the center of everything we do.',
}

export default async function About() {
  let blogArticles = (await loadArticles()).slice(0, 2)

  return (
    <>
      <PageIntro eyebrow="About us" title="KEWR - DIGITAL">
        <p>
          We believe that our strength lies in our collaborative approach, which
          puts our clients at the center of everything we do.
        </p>
        <div className="mt-10 max-w-2xl space-y-6 text-base">
          <p>
            From its humble beginnings in a small town, our company has grown
            into a dynamic hub where tradition meets innovation. Rooted in a
            community that values its rich heritage, we are driven by a powerful
            vision for the future.
          </p>
          <p>
            Our commitment to continuous research and development exemplifies
            our dedication to pushing the boundaries of technology while
            honoring our origins. This blend of past and future fuels our
            ambition to expand, innovate, and lead, proving that great things
            can indeed come from small places.
          </p>
        </div>
      </PageIntro>
      <Container className="mt-16">
        <StatList>
          <StatListItem value="35" label="Underpaid employees" />
          <StatListItem value="52" label="Placated clients" />
          <StatListItem value="$25M" label="Invoices billed" />
        </StatList>
      </Container>

      <Culture />

      {/* <Team /> */}

      <PageLinks
        className="mt-24 sm:mt-32 lg:mt-40"
        title="Our Research"
        intro="Our team of experienced designers and developers has just one thing on their mind; working on your ideas to draw a smile on the face of your users worldwide. From conducting Brand Sprints to UX Design."
        pages={blogArticles}
      />

      <ContactSection />
    </>
  )
}
